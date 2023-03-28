import datetime
import json
import os

from flask import current_app

from tests.conftest import SRC_DIR
from visual import create_app
from visual.core import db
from visual.models import SoftwareDistributionKey, SoftwareVersion, Country, City, User, AuthToken, TeamMember, \
    Department

APPLICATIONS_KEYS = None

with open(os.path.join(SRC_DIR, 'cities_countries.json')) as fm:
    countries = json.load(fm)

def setup_module():
    """
    Исходные данные: Для всех приложений, кроме androidplayer добавим ключ в SoftwareDistributionKey
    Для всех приложений добавим историю версий
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        global APPLICATIONS_KEYS
        APPLICATIONS_KEYS = current_app.config.get('APPLICATIONS')
        db.session.add(Department(title='Dev'))
        db.session.flush()
        users = [
            {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com'},
            {'id': 2, 'name': 'boris', 'email': 'boris@biganto.com', 'team_member': TeamMember(roles=['tours'], department_id=1)},
            {'id': 3, 'name': 'super', 'email': 'super@biganto.com', 'password_hash': User.hash_password('123'), 'team_member': TeamMember(roles=['super'], department_id=1)},
            {'id': 4, 'name': 'banned', 'email': 'banned@biganto.com', 'banned': True},
            {'id': 5, 'name': 'deleted', 'email': 'deleted@biganto.com',
             'deleted': datetime.datetime.now() - datetime.timedelta(days=1)}
        ]
        for kwargs in users:
            user = User(email_confirmed=True, **kwargs)
            user.auth_tokens.append(
                AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30),
                          ip='0.0.0.0'))
            db.session.add(user)
            db.session.flush()
        for key in APPLICATIONS_KEYS.keys():
            if key != 'androidplayer':
                db.session.add(SoftwareDistributionKey(app_id=key, key='some_key'))
            db.session.add(SoftwareVersion(app_id=key, version=[1, 1, 1], filename=f'{key}.app'))
            db.session.add(SoftwareVersion(app_id=key, version=[1, 1, 2], filename=f'{key}.app'))
            db.session.add(SoftwareVersion(app_id=key, version=[2, 1, 2], filename=f'{key}.app'))

        # Заполним справочник countries и cities
        for country in countries['countries']:
            db.session.add(Country(**country))
        db.session.flush()
        for city in countries['cities']:
            db.session.add(City(**city))
        db.session.commit()
        db.session.close()

def test_get_timezone(api):
    """
    Получить список временных зон
    GET /misc/timezones
    """
    resp = api.get(f'/misc/timezones')
    assert resp.status_code == 200


def test_misc_history_apps(api):
    """
    Получить историю версий приложений
    GET /misc/software/<app_id>
    """
    for key in APPLICATIONS_KEYS.keys():
        resp = api.get(f'/misc/software/{key}')
        assert resp.status_code == 200


def test_misc_history_app(api):
    """
    Получить историю версий приложения
    GET /misc/software/<app_id>/version
    """
    for key in APPLICATIONS_KEYS.keys():
        rv = api.get(f'/misc/software/{key}/version')
        assert rv.status_code == 200


def test_misc_get_key(api):
    """
    Получить ключ установки приложения
    GET /misc/software/<app_id>/key
    """
    for key in APPLICATIONS_KEYS.keys():
        # Пытаемся получить ключ приложения.
        # У androidplayer ключ не создавался
        rv = api.get(f'/misc/software/{key}/key')
        if key != 'androidplayer':
            assert rv.status_code == 200
        else:
            assert rv.status_code == 400


def test_get_cities(api):
    """
    Пытаемся получить список городов на языке пользователя
    GET /misc/cities
    :param api:
    :return:
    """
    # Проверим, что если не указан язык, возвращается en
    resp = api.get('/misc/cities')
    assert resp.status_code == 200
    # отберем префиксы имени города отличные от 'en'
    names = [city['name'].split('_')[-1] for city in resp.result if city['name'].split('_')[-1] != 'en']
    assert not names

    query_string = {'lang': 'de'}
    # Проверим, что возвращается 'name' на правильном языке
    resp = api.get('/misc/cities', query_string=query_string)
    assert resp.status_code == 200
    # отберем префиксы имени города отличные от query_string['lang']
    names = [city['name'].split('_')[-1] for city in resp.result if city['name'].split('_')[-1] != query_string['lang']]
    assert not names

    query_string = {'limit': 2}
    # Проверим, что возвращается лимитированное количество
    resp = api.get('/misc/cities', query_string=query_string)
    assert resp.status_code == 200
    # отберем префиксы имени города отличные от query_string['lang']
    names = [city['name'] for city in resp.result]
    assert len(names) == query_string['limit']

    query_string = {'lang': 'ru', 'search': 'ст'}
    # Проверим, что возвращаемый результат содержит query_string['search']
    resp = api.get('/misc/cities', query_string=query_string)
    assert resp.status_code == 200
    names = [city['name'] for city in resp.result]
    for name in names:
        assert query_string['search'].lower() in name.lower()

    query_string = {'lang': 'ru', 'prefix': 'ка'}
    # Проверим, что возвращаемый результат начинается query_string['prefix']
    resp = api.get('/misc/cities', query_string=query_string, _debug=True)
    assert resp.status_code == 200
    names = [city['name'] for city in resp.result]
    for name in names:
        assert name.lower().find(query_string['prefix'].lower()) == 0

    query_string = {'lang': 'ru', 'offset': 1}
    # Проверим, что возвращаемый результат сдвигается на query_string['offset']
    resp = api.get('/misc/cities', query_string=query_string)
    assert resp.status_code == 200
    names = [city['name'] for city in resp.result]
    assert 'Анталья' not in names

