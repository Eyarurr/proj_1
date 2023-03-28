import requests
import traceback
import json

from rauth import OAuth2Service
from flask import render_template, request, redirect, flash, url_for, jsonify, abort, current_app, session
from flask_login import login_user, logout_user, login_required
from flask_babel import gettext

from visual.core import db, csrf
from visual.mail import send_email
from visual.models import User, PasswordRecoveryToken, EmailConfirmToken, UserAuth, UserProduct
from visual.util import defer_cookie
from . import mod, forms


facebook = OAuth2Service(
    name='fb',
    client_id='458996287582580',
    client_secret='f956381084b3d2676bcce5a78b573581',
    authorize_url='https://graph.facebook.com/oauth/authorize',
    access_token_url='https://graph.facebook.com/oauth/access_token',
    base_url='https://graph.facebook.com/',
)

vk = OAuth2Service(
    name='vk',
    client_id='7174431',
    client_secret='zpV3T9TzGtWDtOsUoZk9',
    authorize_url='https://oauth.vk.com/authorize',
    access_token_url='https://oauth.vk.com/access_token',
    base_url='https://api.vk.com/method/',
)


class Service:
    PROVIDERS = {'fb': 'Facebook', 'vk': 'ВКонтакте'}

    @classmethod
    def provider_name(cls, provider):
        return cls.PROVIDERS.get(provider, provider)

    @classmethod
    def factory(cls, provider, *args, **kwargs):
        if provider == 'fb':
            return Facebook(*args, **kwargs)
        elif provider == 'vk':
            return VK(*args, **kwargs)
        else:
            raise NotImplementedError

    def __init__(self, redirect_url):
        self.redirect_url = redirect_url
        self.session = None

    def get_authorize_url(self):
        """Возвращает URL для OAuth-авторизации."""
        raise NotImplementedError

    def get_auth_session(self, code):
        """Создаёт OAuth-сессию с кодом `code`"""
        raise NotImplementedError

    def get_profile(self):
        """Скачивает профиль пользователя. Возвращает словарь с полями:
        - email
        - name
        - remote_id
        - remote_url
        """
        raise NotImplementedError


class Facebook(Service):
    def get_authorize_url(self):
        params = {
            'scope': 'public_profile,email',
            'redirect_uri': self.redirect_url
        }
        return facebook.get_authorize_url(**params)

    def get_auth_session(self, code):
        # Получаем короткоживущий токен...
        short_access_token = facebook.get_access_token(
            decoder=lambda x: json.loads(x.decode()),
            data={
                'code': code,
                'redirect_uri': self.redirect_url
            }
        )

        # ...и меняем его на долгоживущий.
        long_access_token = facebook.get_access_token(
            decoder=lambda x: json.loads(x.decode()),
            data={
                'grant_type': 'fb_exchange_token',
                'fb_exchange_token': short_access_token
            }
        )

        self.session = facebook.get_session(long_access_token)

        return self.session

    def get_profile(self):
        me = self.session.get(
            'me?fields=id,email,name,link'
        ).json()

        profile = {
            'email': me.get('email'),
            'name': me.get('name'),
            'remote_id': me.get('id'),
            'remote_url': me.get('link')
        }
        return profile


class VK(Service):
    def get_authorize_url(self):
        params = {
            'scope': 'friends,email,notifications,offline',
            'redirect_uri': self.redirect_url,
            'response_type': 'code',
            'display': 'page'
        }
        return vk.get_authorize_url(**params)

    def get_auth_session(self, code):
        self.session = vk.get_auth_session(
            decoder=lambda x: json.loads(x.decode()),
            data={
                'code': code,
                'redirect_uri': self.redirect_url
            }
        )
        return self.session

    def get_profile(self):
        atr = json.loads(self.session.access_token_response.text)

        me = self.session.get(
            'users.get',
            params={'fields': 'id,first_name,email,last_name,domain', 'v': '5.102'},
            bearer_auth=False
        ).json()['response'][0]

        profile = {
            'email': atr.get('email'),
            'name': me.get('first_name', '') + ' ' + me.get('last_name', ''),
            'remote_id': str(me.get('id')),
            'remote_url': 'https://vk.com/' + me.get('domain')
        }
        return profile


def add_default_products(user):
    """Создаёт юзеру дефолтные продукты из конфига, добавляет их в сессию."""
    for product_id, data in current_app.config['DEFAULT_PRODUCTS'].items():
        product = UserProduct(user_id=user.id, product_id=product_id, **data)
        db.session.add(product)


@mod.route('/login/', methods=('POST', ))
@csrf.exempt
def login():
    """Авторизация почтои и паролем. Входные данные (POST):
    - email: почта
    - password: пароль
    - is_ajax: если не пустое, то в ответе будет
    - client
    Вернёт либо редирект, либо при is_ajax JSON {'error': ''} или {'redirect': url}
    """
    is_ajax = request.values.get('ajax')
    client = request.args.get('client')

    def success():
        # Для поддержки windows player < 3.0
        if client in ('vrpanoplayer', 'desktopplayer', 'mobileplayer'):
            return 'OK'
        url = request.values.get('next') or url_for('my.index')

        if is_ajax:
            return jsonify(redirect=url)
        else:
            return redirect(url)

    def fail(error):
        # Для поддержки windows player < 3.0
        if client in ('vrpanoplayer', 'desktopplayer', 'mobileplayer'):
            return 'Неверный логин или пароль.', 403
        if is_ajax:
            return jsonify(error=error)
        else:
            flash(error, 'danger')
            return redirect(request.args.get('fail', url_for('my.index')))

    user = User.query.filter(db.func.lower(User.email) == request.form.get('email', '').lower().strip()).first()

    if user and user.password_hash is not None and User.hash_password(request.form.get('password', '')) == user.password_hash:
        if not user.email_confirmed:
            refer = url_for('users.resend_confirm_email', user_id=user.id)
            retry_url = '<a href="{}">{}</a>'.format(refer, gettext("Retry now"))
            return fail(gettext("Please check your inbox for an email with your account activation link.") + '\n' + retry_url)

        if not login_user(user, remember=True):
            return fail(gettext("The password is correct, but your personal account is not active."))
    else:
        return fail(gettext("Incorrect e-mail or password."))

    return success()


@mod.route('/login/<provider>/')
def oauth_login(provider):
    """Вход через OAuth-провайдера. Редиректит на страницу авторизации провайдера.
    """
    defer_cookie('_login_next', request.args.get('next', ''), path='/')
    service = Service.factory(provider, redirect_url=url_for('.oauth_authorized', provider=provider, _external=True))
    return redirect(service.get_authorize_url())


@mod.route('/login/ok/<provider>/')
def oauth_authorized(provider):
    """Сюда OAuth-провайдер редиректнет после успешной авторизации на нём.
    """
    def redirect_url():
        if request.cookies.get('_login_next'):
            return request.cookies.get('_login_next')
        else:
            return url_for('front.index')

    if 'code' not in request.args:
        abort(400)

    try:
        # Получаем авторизационную сессию и профиль пользователя у OAuth-провайдера
        service = Service.factory(provider, redirect_url=url_for('.oauth_authorized', provider=provider, _external=True))
        oauth_session = service.get_auth_session(request.args.get('code'))
        profile = service.get_profile()
    except Exception as e:
        traceback.print_exc()
        flash('Error communicating with OAuth provider.', 'danger')
        return redirect(url_for('front.index'))

    # Авторизация или создание юзера. Строится из словаря с полями
    # email, name, remote_id, remote_url
    if 'email' not in profile:
        flash('There is no email in your OAuth profile. Please try another login.', 'danger')
        return redirect(redirect_url())
    if 'name' not in profile:
        flash('There is no name in your OAuth profile. Please try another login.', 'danger')
        return redirect(redirect_url())

    # Ищем юзера с такой авторизацией (по UserAuth.remote_id)
    user = User.query\
        .join(UserAuth)\
        .filter(UserAuth.provider == provider, UserAuth.remote_id == profile['remote_id'])\
        .first()

    # Если не нашли — регистрируем его
    if not user:
        user = User.query.filter_by(email=profile['email']).first()
        if not user:
            # Пользователя с такой почтой не было
            # Он должен принять пользовательские соглашения
            # Показываем модалку регистрации для oauth
            session['auth-registration-oauth'] = True
            # Сохраняем для использования внутри формы модалки
            session['oauth_name'] = profile['name']
            # Сохраняем значения, чтобы создать пользователя и сессию после сабмита
            session['oauth_profile'] = profile
            session['oauth_provider'] = provider
            session['oauth_access_token'] = oauth_session.access_token

            return redirect(redirect_url())

        auth = UserAuth(
            user=user,
            provider=provider,
            remote_id=profile['remote_id'],
            access_token=oauth_session.access_token,
            url=profile['remote_url']
        )
        db.session.add(auth)
        db.session.commit()

    login_user(user, remember=True)
    flash(gettext('Welcome to biganto.com!'), 'success')

    return redirect(redirect_url())


@mod.route('/register-oauth/', methods=('POST', ))
def register_oauth():
    """
    Регистрация пользователя после успешной авторизазии через oauth.
    Пользователь подтверждает политику приватности и может изменить имя или согласиться на нотификации
    Ожидает получить на вход форму (POST) с полями
    `name`, `email_notifications`.

    Если есть ошибки, возвращает {'errors': [список ошибок]}

    Если ошибок нет, создаёт пользователя, сессию и осуществляет вход пользователя
    """

    # Проверяем данные формы
    errors = []

    name = request.form.get('name', '').strip()
    if name == '':
        errors.append(gettext('Please, introduce yourself.'))

    email_notifications = int(bool(request.form.get('email_notifications', False)))

    if errors:
        return jsonify({'errors': errors})

    # Получаем сохраненные ранее значения
    oauth_profile = session.pop('oauth_profile', False)
    oauth_provider = session.pop('oauth_provider', False)
    oauth_access_token = session.pop('oauth_access_token', False)

    # Создаём юзера
    user = User(
        email=oauth_profile['email'],
        name=name,
        email_notifications=email_notifications,
        email_confirmed=True
    )
    db.session.add(user)
    db.session.flush()

    auth = UserAuth(
        user=user,
        provider=oauth_provider,
        remote_id=oauth_profile['remote_id'],
        access_token=oauth_access_token,
        url=oauth_profile['remote_url']
    )

    db.session.add(auth)

    add_default_products(user)

    db.session.commit()

    login_user(user, remember=True)
    flash(gettext('Welcome to biganto.com!'), 'success')

    return jsonify(user.as_dict())


@mod.route('/logout/')
@login_required
def logout():
    """Разлогинить. Вернёт редирект на морду."""
    logout_user()
    return redirect(url_for('front.index'))


@mod.route('/register/', methods=('GET', 'POST'))
def register():
    """
    Регистрация пользователя емейлом и паролем. Ожидает получить на вход форму (POST) с полями
    `email`, `password`, `name`, `email_notifications`.

    Если есть ошибки, возвращает {'errors': [список ошибок]}

    Если ошибок нет, создаёт пользователя, токен для подтверждения почты и возвращает словарь со свойствами нового
    пользователя. Фронт должен сообщить, что на почту response.email ушла ссылка для подтверждения регистрации.

    В окружениях 'development' и 'stage' при GET-запросе отдаёт форму-прототип для тестирования.
    """
    def verify_recaptcha(recaptcha_response):
        try:
            response = requests.post(current_app.config.get('GOOGLE_RECAPTCHA_VERIFY_URL').format(current_app.config.get('GOOGLE_RECAPTCHA_SECRET_CODE'), recaptcha_response, request.remote_addr), timeout=40)
        except requests.exceptions.ReadTimeout:
            return {'error': 'Captcha verification time out'}

        if response.status_code == 200:
            try:
                response_json = json.loads(response.text)
            except json.JSONDecodeError:
                return {'error': 'Captcha server returned invalid response'}
        else:
            return {'error': 'Captcha server returned status code {}'.format(response.status_code)}

        if response_json['success']:
            return {'status': 'OK'}
        else:
            return {'error': 'Captcha is invalid'}

    # Прототип для тестов
    if request.method == 'GET':
        if current_app.config['ENV'] in ('development', 'stage'):
            return render_template('users/register_prototype.html')
        else:
            abort(400)

    # Проверяем данные формы
    errors = []
    email = request.form.get('email', '').strip().lower()

    recaptcha_verification_response = verify_recaptcha(request.form.get('recaptcha_response'))

    if current_app.config['GOOGLE_RECAPTCHA_ENABLED'] and 'error' in recaptcha_verification_response:
        errors.append(gettext(recaptcha_verification_response['error']))
    if email == '':
        errors.append(gettext('Please enter the email address.'))
    elif '@' not in email:
        errors.append(gettext('The email address is not valid.'))
    name = request.form.get('name', '').strip()
    if name == '':
        errors.append(gettext('Please, introduce yourself.'))

    password = request.form.get('password').strip()
    if len(password) < 6:
        errors.append(gettext('The password should contain at least six characters.'))

    if email:
        existing = User.query.filter(db.func.lower(User.email) == email).first()
        if existing:
            errors.append(gettext('User with this email address already exists.'))

    email_notifications = int(bool(request.form.get('email_notifications', False)))

    if errors:
        return jsonify({'errors': errors})

    # Создаём юзера и токен подтверждения почты
    user = User(
        email=email,
        name=name,
        password_hash=User.hash_password(request.form.get('password')),
        email_notifications=email_notifications,
        email_confirmed=False
    )
    db.session.add(user)
    db.session.flush()

    token = EmailConfirmToken(user_id=user.id)
    token.token = token.gentoken()
    db.session.add(token)

    add_default_products(user)

    db.session.commit()

    # Шлём письмо для подтверждения почты
    template = 'users/email/confirm_email'
    subject = gettext("Confirm email on biganto.com")
    recipients = [user.email]
    token.send(template, subject, recipients)

    return jsonify(user.as_dict())


@mod.route('/register/confirm/')
def confirm_email():
    """Подтверждение почты. Сюда приходят по ссылке из письма, которое присылается при регистрации.
    В GET-параметре `user_id` ожидается ID юзера, в параметре `token` — его токен подтверждения почты.
    Если токен неправильный, ставится flash с сообщением об ошибке и возвращается редирект на морду.
    Если токен правильный — юзер логинится, ставится flash с приветственным сообщением и возвращается редирект на морду.
    """

    token = EmailConfirmToken.query\
        .filter_by(user_id=request.args.get('user_id'), token=request.args.get('token'))\
        .first()
    if not token:
        refer = url_for('users.resend_confirm_email', user_id=request.args.get('user_id'))
        retry_url = '<a href="{}">{}</a>'.format(refer, gettext("Retry now"))
        flash(gettext("The link for sign up confirmation is incorrect or it has been expired.") + ' ' + retry_url, 'danger')
        return redirect(url_for('front.index'))

    token.user.email_confirmed = True
    login_user(token.user, remember=True)
    db.session.delete(token)
    db.session.commit()

    # Шлём письмо с инфо сразу после подтверждения регистрации
    send_email(
        template='users/email/welcome',
        subject=gettext('Welcome to biganto.com!'),
        recipients=[token.user.email],
        user=token.user
    )

    session['welcome'] = True
    return redirect(url_for('front.index'))


@mod.route('/register/resend/')
def resend_confirm_email():
    """Посылает письмо со ссылкой на существующий токен, если токен не успел протухнуть, или
    на новый"""
    user, token = db.session.query(User, EmailConfirmToken).\
        outerjoin(EmailConfirmToken).\
        filter(User.id == request.args.get('user_id')).first_or_404()

    if user.email_confirmed is True:
        return redirect(url_for('front.index'))
    #  токен протух
    if not token:
        token = EmailConfirmToken(user_id=user.id)
        token.token = token.gentoken()
        db.session.add(token)
        db.session.commit()
    # Шлём письмо для подтверждения почты
    template = 'users/email/confirm_email'
    subject = gettext("Confirm email on biganto.com")
    recipients = [user.email]
    token.send(template, subject, recipients)

    return redirect(url_for('front.index'))


@mod.route('/remind/', methods=('GET', 'POST'))
def remind():
    """Страница напоминания пароля. Отправляет письмо со ссылкой на восстановление пароля."""
    form = forms.RemindPasswordForm(request.form)

    if form.validate_on_submit():
        email = form.email.data.lower()
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if not user:
            flash(gettext("The user with this email address is not registered."), 'danger')
        else:
            PasswordRecoveryToken.query.filter_by(user_id=user.id).delete(synchronize_session=False)
            token = PasswordRecoveryToken(user_id=user.id)
            token.token = token.gentoken()
            db.session.add(token)
            db.session.commit()

            send_email(
                template='users/email/restore_password',
                subject=gettext("Password recovery"),
                recipients=[user.email],

                user=user, token=token
            )

            return render_template('users/after_remind.html', user=user)

    return render_template('users/remind.html', form=form)


@mod.route('/restore-password/', methods=('GET', 'POST'))
def restore_password():
    """Восстановление пароля. Сюда приходят по ссылке из письма, отправляемого из `users.remind`.
    ID юзера — в GET-параметре `user_id`, токен для восстановления — в token."""
    token = PasswordRecoveryToken.query\
        .filter_by(user_id=request.args.get('user_id'), token=request.args.get('token'))\
        .first()
    if not token:
        flash(gettext("The link for password recovery is incorrect or it has been expired."), 'danger')
        return redirect(url_for('front.index'))

    form = forms.RestorePasswordForm()

    if form.validate_on_submit():
        if form.password.data != form.password2.data:
            flash(gettext("The passwords do not match"), 'danger')
        else:
            token.user.password_hash = User.hash_password(form.password.data)
            db.session.delete(token)
            db.session.commit()

            login_user(token.user)
            flash(gettext("Your password has been changed."), 'success')
            return redirect(url_for('front.index'))

    return render_template('users/restore_password.html', form=form, token=token)
