"""
Всякая хуйня!
"""
import uuid

from flask_babel import gettext
from flask_login import current_user, login_required
from flask import request, current_app, g, abort

from . import mod, api_response
from visual.models import SoftwareDistributionKey as SDK, SoftwareVersion, City
from visual.core import db, upload_slots_service
from visual.mail import send_email


@mod.route('/misc/timezones')
def misc_get_timezones():
    """
    GET /misc/timezones
    Возвращает список временных зон на языке пользователя:
        [(code, title), ...]
    """
    zones = []
    for code, title in current_app.config['TIMEZONES'].items():
        zones.append({'code': code, 'title': title[g.lang]})

    return api_response(zones)


@mod.route('/misc/software/<app_id>/version')
def misc_appversion(app_id):
    """
    GET /misc/software/<app_id>/version
    Возвращает номер самой последней версии приложения app_id
    """
    info = current_app.config['APPLICATIONS'].get(app_id)
    if not info:
        abort(404, gettext('Unknown client application %(client)s', client=app_id))

    result = {
        'current_version': info['version'],
        'download_url': info['download_url']
    }

    return api_response(result)


@mod.route('/misc/software/<app_id>')
def misc_software(app_id):
    after = request.args.get('after')
    if after:
        try:
            after = [int(x) for x in after.split('.', 2)]
        except ValueError:
            abort(400, gettext('Minimal version in "after" parameter must be in X.Y.Z format containing integers only.'))

    if app_id not in current_app.config['APPLICATIONS']:
        abort(400, gettext('Unknown application "%(app_id)s".', app_id=app_id))

    q = SoftwareVersion.query
    if after:
        q = q.filter(SoftwareVersion.version > after)

    result = []
    for sw in q.all():
        item = {
            'version': '.'.join([str(_) for _ in sw.version])
        }
        if sw.download_url:
            item['download_url'] = sw.download_url
        else:
            item['download_url'] = sw.file.url
            item['filename'] = sw.filename
            item['filesize'] = sw.filesize

        result.append(item)

    return api_response(result)


@mod.route('/misc/software/<app_id>/key')
def misc_get_key(app_id):
    user_id = current_user.id if current_user.is_authenticated else None

    if app_id not in current_app.config['APPLICATIONS']:
        abort(404, gettext('Wrong product'))

    key = SDK.query.\
        filter(SDK.app_id == app_id).\
        filter(SDK.used == None).\
        order_by(SDK.created).\
        first()

    if not key:
        abort(400, gettext('We are out of keys for this product at the moment, please try again later'))
    else:
        SDK.query.filter(SDK.id == key.id).\
            update({'used': db.func.now(), 'used_by': user_id}, synchronize_session=False)
        db.session.commit()

    active_keys_count = db.session.query(db.func.count('*')).filter(SDK.app_id == app_id, SDK.used == None).scalar()
    if active_keys_count < 10:
        send_email(
            'Заканчиваются ключи для платформы %s' % app_id,
            [current_app.config['MAIL_MANAGER']],
            template='mail/keys_low_amount',
            product=app_id
        )

    result = {
        'key': key.key,
        'app_id': app_id
    }

    return api_response(result)


def find_upload_server(options):
    """
    Перебирает все сервера из конфига UPLOAD_SERVER и возвращает первый подходящий под фильтры в options.
    options — словарь с GET-параметрами запроса POST /upload-slots
    :param options:
    :return:
    """
    requested_protocols = options.get('protocols')
    if requested_protocols:
        requested_protocols = set(requested_protocols.split(','))

    for server in current_app.config['UPLOAD_SERVERS']:
        if requested_protocols and server['protocol'] not in requested_protocols:
            continue

        return server

    return None


@mod.route('/upload-slots', methods=('POST', ))
@login_required
def post_upload_slots():
    """
    Создаёт загрузочный слот и возвращает его свойства.
    :return:
    """
    # Перебираем все сервера и ищем подходящий
    server = find_upload_server(request.args)
    if not server:
        abort(400, gettext('There are no servers supporting your requirements.'))

    verify_slot_creation = bool(request.args.get('verify'))
    warnings = []

    # Просим сервис управления Upload-серверами создать слот
    slot = str(uuid.uuid4())
    verified = upload_slots_service.create_slot(server, slot, verify_dir=verify_slot_creation)
    if verify_slot_creation and not verified:
        warnings.append(gettext('Slot creation not verified.'))

    result = {
        'protocol': server['protocol'],
        'user':  server['user'],
        'host': server['host'],
        'basedir': server['remote_basedir'],
        'slot': slot
    }
    if 'port' in server:
        result['port'] = server['port']

    return api_response(result, warnings=warnings)


@mod.route('/my/permissions/filincam/scene.upload')
@login_required
def permissions_filincam_scene_upload():
    return api_response(True)


@mod.route('/misc/cities')
def misc_get_cities():
    """
    Возвращает список городов на языке пользователя
    GET /misc/cities
    """
    result = []
    q = db.session.query(City).order_by(City.name)
    if request.args.get('search', None):
        q = q.filter(City.name.ilike('%' + str(request.args.get("search")) + '%'))

    if request.args.get('prefix', None):
        q = q.filter(City.name.ilike(str(request.args.get("prefix")) + '%'))

    if request.args.get('country_id', None):
        country_id = request.args.get('country_id').upper()
        q = q.filter(City.country_id == country_id)

    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 500, type=int)

    q = q.limit(limit).offset(offset)
    for city in q.all():
        result.append(city.api_view())

    return api_response(result)