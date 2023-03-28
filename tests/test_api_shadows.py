import os
import datetime

import pytest

from tests.common import set_flow
from tests.conftest import SRC_DIR
from visual import create_app
from visual.core import db
from visual.models import User, Footage, Tour, TeamMember, AuthToken
from visual.util import unzip_footage_tour

datasets = {
    'put_shadow_add': [
        {'id': 1, 
         'body': {'title': 'add shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'center', 'wurst@render_type': 'vray'
                       }}}
         },
        {'id': 2, 
         'body': {'title': 'add shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'left', 'wurst@render_type': 'vray'
                       }}}
         },
        {'id': 3, 
         'body': {'title': 'add shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'right', 'wurst@render_type': 'vray'
                       }}}
         },
        {'id': 4, 
         'body': {'title': 'add shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'center', 'wurst@render_type': 'corona'
                       }}}
         },
        {'id': 5, 
         'body': {'title': 'add shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'left', 'wurst@render_type': 'corona'
                       }}}
         },
        {'id': 6, 
         'body': {'title': 'add shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'right', 'wurst@render_type': 'corona'
                       }}}
         },
    ],
    'put_shadow_modify': [
        {'id': 1, 
         'body': {'title': 'modify shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama1536.png', 'wurst@eye': 'center', 'wurst@render_type': 'vray'
                       }}}
         },
        {'id': 2, 
         'body': {'title': 'modify shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama1536.png', 'wurst@eye': 'left', 'wurst@render_type': 'vray'
                       }}}
         },
        {'id': 3, 
         'body': {'title': 'modify shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama1536.png', 'wurst@eye': 'right', 'wurst@render_type': 'vray'
                       }}}
         },
        {'id': 4, 
         'body': {'title': 'modify shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama1536.png', 'wurst@eye': 'center', 'wurst@render_type': 'corona'
                       }}}
         },
        {'id': 5, 
         'body': {'title': 'modify shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama1536.png', 'wurst@eye': 'left', 'wurst@render_type': 'corona'
                       }}}
         },
        {'id': 6, 
         'body': {'title': 'modify shadow', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2}, 'panoramas': {
                 '1': {'wurst@flow': 'TOKEN/panorama1536.png', 'wurst@eye': 'right', 'wurst@render_type': 'corona'
                       }}}
         },
    ],
}

USERS = {}
FOOTAGES = {}


def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3 - нормальные, 4 - забаненный и 5 - удалённый
    Создаем по одному туры и по одной съемке каждому юзеру. В каждую съемку распаковываем тур.
    :return:
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.expire_on_commit = False

        users = [
            {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com'},
            {'id': 2, 'name': 'boris', 'email': 'boris@biganto.com', 'team_member': TeamMember(roles=['tours'])},
            {'id': 3, 'name': 'super', 'email': 'super@biganto.com', 'password_hash': User.hash_password('123')},
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
            tour = Tour(id=user.id, user_id=user.id, title='tour',
                        footage=Footage(user_id=user.id, _status='testing', type='real'))
            db.session.add(tour)
            db.session.flush()
            tour.mkdir()
            tour.footage.mkdir()
            path = os.path.join(SRC_DIR, 'tours', 'tour-20335.zip')
            unzip_footage_tour(path, footage=tour.footage, tour=tour)

            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            FOOTAGES[tour.footage_id] = {k: getattr(tour.footage, k) for k in ('id', 'user_id',)}
            FOOTAGES[tour.footage_id].update({'in_files': tour.footage.in_files()})

        db.session.commit()
        db.session.close()


@pytest.mark.access
def test_access_shadow(api):
    for user_id, user in USERS.items():
        footage_id = user_id
        shadow_id = footage_id
        skybox_id = 1

        # Описание: Пытаемся ДОБАВИТЬ тень в скайбокс.
        # Параметры: Без токена авторизации
        # Ожидаемый результат: 403
        resp = api.put(f'/footages/{footage_id}/virtual/shadows/{shadow_id}')
        assert resp.status_code == 403

        # Описание: Пытаемся ИЗМЕНИТЬ тень в скайбоксе.
        # Параметры: Без токена авторизации
        # Ожидаемый результат: 403
        resp = api.put(f'/footages/{footage_id}/virtual/shadows/{shadow_id}')
        assert resp.status_code == 403

        # Описание: Пытаемся удалить тень из скайбокса.
        # Параметры: Без токена авторизации
        # Ожидаемый результат: 403
        resp = api.delete(f'/footages/{footage_id}/virtual/shadows/{shadow_id}/{skybox_id}')
        assert resp.status_code == 403

        # Описание: Пытаемся удалить тень из съемки.
        # Параметры: Без токена авторизации
        # Ожидаемый результат: 403
        resp = api.delete(f'/footages/{footage_id}/virtual/shadows/{shadow_id}')
        assert resp.status_code == 403


def test_put_shadow(api):
    """
    Сохранить тень
    PUT /footages/<footage_id>/virtual/shadows/<shadow_id>
    """
    for user_id, user in USERS.items():
        footage_id = user_id
        for dataset in datasets['put_shadow_add']:
            shadow_id = dataset['id']

            # Описание: Пытаемся ДОБАВИТЬ тень в скайбокс.
            # Параметры: С токеном авторизации
            # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может ДОБАВИТЬ тень в скайбокс
            set_flow({'TOKEN': ['src/panorama.png']})
            resp = api.put(f'/footages/{footage_id}/virtual/shadows/{shadow_id}', body=dataset['body'], auth_as=user['email'])
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 200
                # Проверяем, что файлы панорам добавляются в папку in_files\shadows
                path = os.path.join(FOOTAGES[footage_id]['in_files'], 'shadows')
                assert os.path.exists(path)
                assert os.path.isdir(path)
                assert list(os.listdir(path))

        for dataset in datasets['put_shadow_modify']:
            shadow_id = dataset['id']

            # Описание: Пытаемся ИЗМЕНИТЬ тень в скайбоксе.
            # Параметры: С токеном авторизации
            # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может ИЗМЕНИТЬ тень в скайбоксе
            set_flow({'TOKEN': ['src/panorama1536.png']})
            resp = api.put(f'/footages/{footage_id}/virtual/shadows/{shadow_id}', body=dataset['body'], auth_as=user['email'])
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 200


def test_delete_shadow_from_skybox(api):
    """
    Удалим тень из скайбокса
    DELETE /footages/<footage_id>/virtual/shadows/<shadow_id>/<skybox_id>
    """
    for user_id, user in USERS.items():
        footage_id = user_id
        skybox_id = 1
        for dataset in datasets['put_shadow_add']:
            shadow_id = dataset["id"]

            # Описание: Пытаемся удалить тень из скайбокса.
            # Параметры: С токеном авторизации
            # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может удалить тень из скайбокса
            resp = api.delete(f'/footages/{footage_id}/virtual/shadows/{shadow_id}/{skybox_id}', auth_as=user['email'],)
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 204


def test_delete_shadow_from_footage(api):
    """
    Удаляет тень из съемки
    DELETE /footages/<footage_id>/virtual/shadows/<shadow_id>
    """
    for user_id, user in USERS.items():
        footage_id = user_id
        for dataset in datasets['put_shadow_add']:
            shadow_id = dataset["id"]

            # Описание: Пытаемся удалить тень из съемки.
            # Параметры: С токеном авторизации
            # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может удалить тень из съемки
            resp = api.delete(f'/footages/{footage_id}/virtual/shadows/{shadow_id}', auth_as=user['email'])
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 204
                # Проверяем, что директория shadows очищена от файлов
                path = os.path.join(FOOTAGES[footage_id]['in_files'], 'shadows')
                assert os.path.exists(path)
                assert shadow_id not in os.listdir(path)


@pytest.mark.bad_requests
def test_exceptions(api):
    """
    Плохие запросы.
    """
    body = {'title': 'raise_exceptions', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2},
            'panoramas': {
                '1': {'wurst@flow': 'TOKEN/panorama1.png', 'wurst@eye': 'center', 'wurst@render_type': 'vray'
                      }}}
    user_id = 3
    user = USERS[user_id]
    footage_id = user_id
    shadow_id = 1
    params = {'body': body, 'auth_as': user['email']}

    # Описание задачи: Пытаемся ДОБАВИТЬ тень в скайбокс.
    # Параметр: Нет файла в TOKEN
    resp = api.put(f'/footages/{footage_id}/virtual/shadows/{shadow_id}', **params)
    assert resp.status_code == 400
    assert resp.has_error('Source file TOKEN/panorama1.png not found for wurst@flow.')

    """"""
    body = {'title': 'raise_exceptions', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2},
            'panoramas': {
                '1': {'wurst@eye': 'center', 'wurst@render_type': 'vray'
                      }}}
    params = {'body': body, 'auth_as': user['email']}
    # Описание задачи: Пытаемся ДОБАВИТЬ тень в скайбокс.
    # Параметр: Нет 'wurst@flow'
    resp = api.put(f'/footages/{footage_id}/virtual/shadows/{shadow_id}', **params)
    assert resp.status_code == 400
    assert resp.has_error('Malformed wurst@flow value.')

    """"""
    body = {'title': 'raise_exceptions', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 33.2},
            'panoramas': {
                '1': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@render_type': 'vray'
                      }}}

    params = {'body': body, 'auth_as': user['email']}
    # Описание задачи: Пытаемся ДОБАВИТЬ тень в скайбокс.
    # Параметр: Нет wurst@eye
    set_flow({'TOKEN': ['src/panorama.png']})
    resp = api.put(f'/footages/{footage_id}/virtual/shadows/{shadow_id}', **params)
    assert resp.status_code == 400
    assert resp.has_error('Invalid wurst@eye value')

    """"""
    body = {'title': 'raise_exceptions', 'disabled': False, 'enter': {'effect': 'made', 'speed': 33.2},
            'panoramas': {
                '1': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'center',
                      }}}
    params = {'body': body, 'auth_as': user['email']}
    
    # Описание задачи: Пытаемся ДОБАВИТЬ тень в скайбокс.
    # Параметр: effect не fade
    set_flow({'TOKEN': ['src/panorama.png']})
    resp = api.put(f'/footages/{footage_id}/virtual/shadows/{shadow_id}', **params)
    assert resp.status_code == 400
    assert resp.has_error('Invalid effect \"made\"')

    """"""
    body = {'title': 'raise_exceptions', 'disabled': False, 'enter': {'effect': 'fade', 'speed': 2}, 
            'some_prop': 'some_val', 'panoramas': {
                '1': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'center',
                      }}}
    params = {'body': body, 'auth_as': user['email']}

    # Описание задачи: Пытаемся ДОБАВИТЬ тень в скайбокс.
    # Параметр: Неизвестное свойство some_prop
    set_flow({'TOKEN': ['src/panorama.png']})
    resp = api.put(f'/footages/{footage_id}/virtual/shadows/{shadow_id}', **params)
    assert resp.status_code == 200
    assert resp.has_warning('Unknown input property some_prop')

    """"""
    skybox_id = 100
    # Описание задачи: Пытаемся удалить тень из скайбокса.
    # Параметр: нет такого скайбокса
    resp = api.delete(f'/footages/{footage_id}/virtual/shadows/{shadow_id}/{skybox_id}', **params)
    assert resp.status_code == 404
    assert resp.has_error('Skybox 100 not found.')

    """"""
    skybox_id = 1
    shadow_id = 100
    # Описание задачи: Пытаемся удалить тень из скайбокса.
    # Параметр: нет такой тени
    resp = api.delete(f'/footages/{footage_id}/virtual/shadows/{shadow_id}/{skybox_id}', **params)
    assert resp.status_code == 404
    assert resp.has_error('Shadow 100 not found.')

    """"""
    # Описание задачи: Пытаемся удалить тень из съемки
    # Параметр: нет такой тени
    shadow_id = 100
    resp = api.delete(f'/footages/{footage_id}/virtual/shadows/{shadow_id}', **params)
    assert resp.status_code == 404
    assert resp.has_error('Shadow 100 not found.')
