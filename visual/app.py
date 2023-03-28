import os
import datetime
import functools
import subprocess
import logging
import logging.config
import logging.handlers

from pytz import timezone
from flask.json import JSONEncoder
from flask import Flask, g, request, flash, render_template, jsonify, get_flashed_messages
from flask_login import current_user
import flask_sa_logger
import stripe
import colors
from werkzeug.exceptions import HTTPException
from pillow_heif import register_heif_opener

from .jinja import register_jinja_filters
from .core import db, csrf, storage, babel, products
from .hooks import init_hooks
from .util import defer_cookie
from visual.api_deprecated import errors


class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):
        try:
            if isinstance(obj, datetime.date):
                return obj.isoformat()
            if isinstance(obj, datetime.time):
                return obj.isoformat()
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)


def create_app(cfg=None, purpose=None):
    """Application factory
    """
    app = Flask(__name__)
    app.purpose = purpose
    load_config(app, cfg)
    app.jinja_env.policies['json.dumps_kwargs'] = {'sort_keys': True, 'ensure_ascii': False}

    # logging.config.dictConfig(app.config['LOGGING'])

    get_release_version(app)

    app.json_encoder = CustomJSONEncoder

    flask_sa_logger.init_logging(app)

    # Core components
    db.init_app(app)

    # Initialize models
    with app.app_context():
        from . import models

    csrf.init_app(app)

    init_babel(app)

    init_login(app)

    register_blueprints(app)

    register_jinja_filters(app)

    storage.init_app(app)

    init_hooks(app)

    init_logging(app)

    register_heif_opener()

    products.init_app(app)

    app.logger.info('visual %s загружен' % app.config['ENV'])

    return app


def register_blueprints(app):
    from . import front, virtoaster, admin, users, my, api_deprecated, tutorials, support, api3

    modules = (front, virtoaster, admin, users, my, api_deprecated, tutorials, support, api3)

    for m in modules:
        app.register_blueprint(m.mod)

    @app.errorhandler(HTTPException)
    def http_exception_handler(e):
        """
        Обработчик HTTP Exception'ов.
        Для рендера кастомного шаблона ошибки, в e.description можно передать строку "@custom-template",
        тогда отрендерится шаблон `http_errors/{e.code}-{custom-template}.html`.
        """
        # Для API возвращаем ошибку в JSON.
        if request.blueprint == 'api3' or request.path.startswith('/api/v3'):
            return jsonify({'errors': [str(e.description)]}), e.code

        # Для всего остального рендерим шаблон страницы с ошибкой
        if e.description.startswith('@'):
            custom_template = e.description[1:]
            return render_template(f'http_errors/{e.code}-{custom_template}.html', e=e), e.code
        else:
            return render_template('http_errors/http_error.html', e=e), e.code


def load_config(app, cfg=None):
    """Загружает в app конфиг из config.py, а потом обновляет его py-файла в cfg или, если он не указан, из переменной
    окружения VISUAL_CFG
    """
    app.config.from_pyfile('config.py')

    if os.path.isfile(os.path.join(app.root_path, 'config.local.py')):
        app.config.from_pyfile('config.local.py')

    if cfg is None and 'VISUAL_CFG' in os.environ:
        cfg = os.environ['VISUAL_CFG']

    if cfg is not None:
        app.config.from_pyfile(cfg)

    stripe.api_key = app.config.get('STRIPE_SK')

    # Чтобы не было конфликтов кук между доменом и поддоменами, форсим значение SESSION_COOKIE_DOMAIN
    app.config['SESSION_COOKIE_DOMAIN'] = app.config.get('SERVER_NAME')


def init_login(app):
    from .core import login_manager, db
    from visual.models import User
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.options(db.joinedload(User.team_member)).get(user_id)

    @login_manager.request_loader
    def request_loader(request):
        token = request.args.get('auth_token')
        if token:
            user, g.auth_error_code, g.auth_error_message = User.load_from_api_token(token)
            return user
        else:
            return None

    def unauthorized():
        # Для запросов API отдаём ошибку
        if request.blueprint == 'api3':
            # Код ошибки из api_deprecated.errors => HTTP-код ответа
            error_codes = {
                errors.AUTH_REQUIRED: 401,
                errors.AUTH_BAD_TOKEN: 401,
                errors.AUTH_USER_NOT_FOUND: 401,
                errors.AUTH_BAD_SIGNATURE: 401,
                errors.AUTH_USER_BANNED: 403,
                errors.AUTH_USER_EMAIL_NOT_CONFIRMED: 403,
            }
            return jsonify({'errors': [g.get('auth_error_message', 'Unauthorized')]}), error_codes.get(g.get('auth_error_code'), 403)
        elif request.blueprint == 'api_deprecated':
            return jsonify({
                'errors': [
                    {
                        'code': g.get('auth_error_code', 403),
                        'message': g.get('auth_error_message', 'Unauthorized')
                    }
                ]
            })
        else:
            # А это для всех обычных запросов
            return render_template('http_errors/401.html'), 401

    login_manager.unauthorized_callback = unauthorized


def init_babel(app):
    babel.init_app(app)

    @app.before_request
    def set_lang():
        g.lang = locale_selector()

        # Запоминаем вычисленный язык в куке
        if 'lang' not in request.cookies or request.cookies['lang'] != g.lang:
            defer_cookie('lang', g.lang, max_age=60 * 60 * 24 * 365 * 3)

        # Запоминаем вычисленный язык в current_user.lang
        if current_user.is_authenticated and current_user.lang != g.lang:
            current_user.lang = g.lang
            db.session.commit()

    def choose_lang_from_request():
        """Выбирает язык из запроса: GET, Cookie, current_user, Accept-Languages"""
        # Проверяем GET-параметр
        lang = request.args.get('lang')
        browser_lang = request.accept_languages.best_match(app.config['LANGUAGES'].keys())
        if lang in app.config['LANGUAGES']:
            if 'lang' not in request.cookies:
                defer_cookie('lang', lang, max_age=60 * 60 * 24 * 365 * 3)
            return lang

        # Проверяем куку
        elif 'lang' in request.cookies and request.cookies['lang'] in app.config['LANGUAGES']:
            return request.cookies['lang']

        # Юзер
        elif current_user.is_authenticated and current_user.lang is not None and current_user.lang in app.config['LANGUAGES']:
            return current_user.lang

        # Проверяем язык браузера
        elif browser_lang:
            return browser_lang

        else:
            return app.config['LANGUAGE']

        # # Если ничто в запросе не намекает на язык, возвращаем дефолтный
        return app.config['LANGUAGE']

    @babel.localeselector
    def locale_selector():
        if 'lang_forced' in g:
            return g.lang_forced

        # Если работаем в контексте запроса, то язык вычисляется из свойств запроса
        if request:
            lang = choose_lang_from_request()

            # В эндпоинтах сайта не позволяем реквестом выбирать язык, который не поддерживается сайтом
            # @todo: возможно все эндпоинты сайта удобнее засунуть в один блюпринт и эту проверку делать в нём
            if request.blueprint in ('front', 'virtoaster', 'users', 'my', 'tutorials', 'support'):
                lang_config = app.config['LANGUAGES'].get(lang, {})
                if 'applicable' in lang_config and 'site' not in lang_config['applicable']:
                    return app.config['LANGUAGE']
            return lang
        else:
            return app.config['LANGUAGE']

    @babel.timezoneselector
    def get_timezone():
        if current_user is not None and current_user.is_authenticated:
            return timezone(current_user.timezone or 'UTC')
        else:
            return timezone('UTC')


class ColoredLogFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': functools.partial(colors.color, fg='white', style='faint'),
        'INFO': colors.green,
        'WARNING': colors.yellow,
        'ERROR': colors.red,
        'CRITICAL': functools.partial(colors.color, fg='white', bg='red')
    }

    def format(self, record):
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = self.COLORS[levelname](levelname)
        return logging.Formatter.format(self, record)


def init_logging(app):
    """Инициализирует логгеры.
    """
    # Статистика
    log_stat = logging.getLogger('statistics')
    log_stat.setLevel(logging.DEBUG)
    log_stat.propagate = False

    sh = logging.StreamHandler()
    sh.setFormatter(ColoredLogFormatter(colors.blue(' * ') + 'STAT %(asctime)s - %(levelname)s - %(message)s'))
    sh.setLevel(app.config.get('STAT_LOG_LEVEL'))
    log_stat.addHandler(sh)

    if app.config.get('STAT_LOG_EMAIL'):
        eh = logging.handlers.SMTPHandler(app.config.get('MAIL_SERVER'), app.config.get('MAIL_DEFAULT_SENDER'), app.config.get('STAT_LOG_EMAIL'), 'Email LOG')
        eh.setLevel(app.config.get('STAT_LOG_EMAIL_LEVEL'))
        eh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        log_stat.addHandler(eh)

    # Сборщики туров
    log_builder = logging.getLogger('builder')
    log_builder.setLevel(logging.DEBUG)
    log_builder.propagate = False

    sh = logging.StreamHandler()
    sh.setFormatter(ColoredLogFormatter(colors.green(' * ') + 'BUILDER %(asctime)s - %(levelname)s - %(message)s'))
    sh.setLevel(app.config.get('BUILDER_LOG_STREAM_LEVEL'))
    log_builder.addHandler(sh)

    if app.config.get('BUILDER_LOG_FILE'):
        fh = logging.FileHandler(app.config.get('BUILDER_LOG_FILE'))
        fh.setLevel(app.config.get('BUILDER_LOG_FILE_LEVEL'))
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        log_builder.addHandler(fh)

    if app.config.get('BUILDER_LOG_EMAIL'):
        eh = logging.handlers.SMTPHandler(app.config.get('MAIL_SERVER'), app.config.get('MAIL_DEFAULT_SENDER'), app.config.get('BUILDER_LOG_EMAIL'), 'Builder LOG')
        eh.setLevel(app.config.get('BUILDER_LOG_EMAIL_LEVEL'))
        eh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        log_builder.addHandler(eh)

    # Процессинг filincam
    log_builder = logging.getLogger('filincam')
    log_builder.setLevel(logging.DEBUG)
    log_builder.propagate = False

    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter('FILINCAM %(asctime)s - %(levelname)s - %(message)s'))
    sh.setLevel(app.config.get('FILINCAM_LOG_STREAM_LEVEL'))
    log_builder.addHandler(sh)

    if app.config.get('FILINCAM_LOG_FILE'):
        fh = logging.FileHandler(app.config.get('FILINCAM_LOG_FILE'))
        fh.setLevel(app.config.get('FILINCAM_LOG_FILE_LEVEL'))
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        log_builder.addHandler(fh)

    # Биллинг
    log_billing = logging.getLogger('billing')
    log_billing.setLevel(logging.DEBUG)
    log_billing.propagate = False

    sh = logging.StreamHandler()
    sh.setFormatter(ColoredLogFormatter(colors.white(' * ') + 'BILLING %(asctime)s - %(levelname)s - %(message)s'))
    sh.setLevel(app.config.get('BILLING_LOG_STREAM_LEVEL'))
    log_billing.addHandler(sh)

    if app.config.get('BILLING_LOG_FILE'):
        fh = logging.FileHandler(app.config.get('BILLING_LOG_FILE'))
        fh.setLevel(app.config.get('BILLING_LOG_FILE_LEVEL'))
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        log_billing.addHandler(fh)

    if app.config.get('BILLING_LOG_EMAIL'):
        eh = logging.handlers.SMTPHandler(app.config.get('MAIL_SERVER'), app.config.get('MAIL_DEFAULT_SENDER'), app.config.get('BILLING_LOG_EMAIL'), 'Billing LOG')
        eh.setLevel(app.config.get('BILLING_LOG_EMAIL_LEVEL'))
        eh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        log_billing.addHandler(eh)

    # Misc
    log_misc = logging.getLogger('misc')
    log_misc.setLevel(logging.DEBUG)
    log_misc.propagate = False

    if app.config.get('MISC_LOG_FILE'):
        fh = logging.FileHandler(app.config.get('MISC_LOG_FILE'))
        fh.setLevel(app.config.get('MISC_LOG_FILE_LEVEL'))
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        log_misc.addHandler(fh)

    # Misc
    log_microservices = logging.getLogger('microservices')
    log_microservices.setLevel(logging.DEBUG)
    log_microservices.propagate = False

    if app.config.get('MICROSERVICES_LOG_FILE'):
        fh = logging.FileHandler(app.config.get('MICROSERVICES_LOG_FILE'))
        fh.setLevel(app.config.get('MICROSERVICES_LOG_FILE_LEVEL'))
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        log_microservices.addHandler(fh)


def get_release_version(app):
    try:
        basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        # Достаём ID последнего коммита из git rev-parse HEAD
        run = subprocess.run(['git', '-C', basedir, 'rev-parse', '--verify', 'HEAD'], universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if run.returncode != 0 or not run.stdout:
            raise Exception('git rev-parse HEAD error: {}'.format(run.stderr))
        version = run.stdout.strip()
    except (Exception, IOError) as e:
        logging.warning("Can't get last commit id: {}".format(e))
        version = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')

    app.config['RELEASE_VERSION'] = version
