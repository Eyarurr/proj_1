import datetime

import pytest

from visual import create_app
from visual.core import db
from visual.models import User, UserSettings, TeamMember, Footage, AuthToken


def setup_module():
    """
    Добавляем тупо одного юзера, с которым и экспериментируем
    Всякая хуета про доступ - в тестах test_api_users.
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.expire_on_commit = False

        users = [
                {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com', 'team_member': TeamMember(roles=['admin.access'])},
            ]
        for kwargs in users:
            user = User(email_confirmed=True, password_hash=User.hash_password('123'), **kwargs, )
            db.session.add(user)
            db.session.flush()
            token = AuthToken(user_id=user.id, signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30), ip='0.0.0.0')
            db.session.add(token)
            db.session.flush()
        db.session.commit()
        db.session.close()


def test_get_settings(api):
    """
    GET /my
    Ожидаем, что у свежесозданного юзера будут дефолтные сеттинги
    """
    resp = api.get(f'/my', auth_as='anna@biganto.com', _debug=True)
    assert resp.status_code == 200
    default_settings = UserSettings()
    assert resp.result['settings']['news_last_seen'] == default_settings.news_last_seen
    assert resp.result['settings']['filincam']['autoprocess'] == default_settings.filincam.autoprocess
    assert resp.result['settings']['filincam']['export_tour']['enabled'] == default_settings.filincam.export_tour.enabled
    assert resp.result['settings']['filincam']['export_tour']['blur_faces'] == default_settings.filincam.export_tour.blur_faces
    assert resp.result['settings']['filincam']['export_tour']['blur_plates'] == default_settings.filincam.export_tour.blur_plates
    assert resp.result['settings']['filincam']['export_tour']['folder_id'] == default_settings.filincam.export_tour.folder_id

    resp = api.get(f'/my', auth_as='anna@biganto.com', query_string={'settings': 'nodefault'})
    assert resp.status_code == 200
    assert resp.result['settings'] == {}


def test_put_settings_bad(api):
    bodies = [
        {'news_last_seen': 'ты хуй'},
        {'filincam': None},
        {'filincam': {'export_tour': {'folder_id': 'не число'}}},
    ]
    for body in bodies:
        resp = api.put(f'/my', body={'settings': body}, auth_as='anna@biganto.com')
        assert resp.status_code == 400, f'{body} - {resp.object}'


def test_put_settings_good(api):
    settings = {
        'news_last_seen': '2021-01-01 15:00',
        'filincam': {
            'autoprocess': False,
            'export_tour': {
                'blur_faces': False,
                'blur_plates': True,
                'enabled': False,
                'folder_id': 323
            }
        },
        'domhub': {
            'crm': {
                'headers': {
                    'First': 'One',
                    'Last': 'Two'
                },
                'get_estate': {
                    'method': 'POST',
                    'url': 'http://pornhub.com/'
                }
            }
        }
    }
    resp = api.put(f'/my', body={'settings': settings}, auth_as='anna@biganto.com')
    assert resp.status_code == 200, resp.object
    assert resp.result['settings']['filincam']['autoprocess'] == False
    assert resp.result['settings']['filincam']['export_tour']['blur_faces'] == False
    assert resp.result['settings']['filincam']['export_tour']['blur_plates'] == True
    assert resp.result['settings']['filincam']['export_tour']['enabled'] == False
    assert resp.result['settings']['filincam']['export_tour']['folder_id'] == 323
    assert resp.result['settings']['domhub']['crm']['get_estate']['method'] == 'POST'

    resp = api.put(f'/my', body={'settings': {'filincam': {'export_tour': {'folder_id': 777}}}}, auth_as='anna@biganto.com')
    assert resp.status_code == 200, resp.object
    assert resp.result['settings']['filincam']['export_tour']['folder_id'] == 777
