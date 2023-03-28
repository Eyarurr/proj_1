"""
https://gitlab.biganto.com/p/docs/wikis/models/ActiveMesh
https://gitlab.biganto.com/p/docs/wikis/api3/outside_active_meshes
"""
import datetime
import pytest

from visual import create_app
from visual.core import db
from visual.models import User, TeamMember, AuthToken, Tour, Footage

USERS = {}
TOURS = {}


def setup_module():
    """
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
             'deleted': datetime.datetime.now() - datetime.timedelta(days=1)},
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

            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title')}

        db.session.commit()
        db.session.close()

@pytest.mark.access
def test_access(api):
    tour_id = 1
    active_mesh = 'active_mesh'
    # Описание задачи: Пробуем ДОБАВИТЬ меш в тур
    # Параметры: без авторизации
    # Ожидаемый результат: 403
    resp = api.put(f'/tours/{tour_id}/active_meshes/{active_mesh}')
    assert resp.status_code == 403

    # Описание задачи: Пробуем удалить меш
    # Параметр: Нет авторизации
    # Ожидаемый результат: 403
    resp = api.delete(f'/tours/{tour_id}/active_meshes/{active_mesh}')
    assert resp.status_code == 403


def test_put_active_mesh(api):
    """
    Добавление и изменение меша
    PUT /tours/<int:tour_id>/active_meshes/<mesh_id>
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        active_mesh = 'ActivMesh0001'
        body = {'title': 'Добавим новый active_mesh', "actions": {"click": "6"}, "class": ["ad"],
                "hover": {"hide_cursor": True}, "type": "mesh", "name": "имя мешa",
                "active_when": {"fill": 'rgba=[10,20,123,0]'}, "look": {"fill": 'rgba=[10,20,0,0]'}
                }
        # Описание задачи: Пробуем ДОБАВИТЬ меш в тур
        # Параметр: с авторизацией
        # Ожидаемый результат: все авторизованные юзеры, кроме забаненного могут добавить себе меш
        resp = api.put(f'/tours/{tour_id}/active_meshes/{active_mesh}', body=body, auth_as=user['email'])
        if not user['banned']:
            assert resp.status_code == 200
        else:
            assert resp.status_code == 403

        # Описание задачи: Пробуем ИЗМЕНИТЬ меш в туре
        # Ожидаемый результат: все авторизованные юзеры, кроме забаненного могут добавить себе меш
        body.update({'title': 'Изменим имя для active_mesh', "name": "новое имя мешa"})
        resp = api.put(f'/tours/{tour_id}/active_meshes/{active_mesh}', body=body, auth_as=user['email'])
        if not user['banned']:
            assert resp.status_code == 200
        else:
            assert resp.status_code == 403


def test_get_active_mesh(api):
    """
    Получить один активный меш тура
    GET /tours/<int:tour_id>/active_meshes/<mesh_id>
    """
    active_mesh = 'ActivMesh0001'
    for user_id, user in USERS.items():
        tour_id = user_id

        # Описание задачи: Пробуем получить один меш тура
        # Параметр: нет авторизации
        # Ожидаемый результат: Получить меш можно у любого тура, кроме как у забаненного и удаленного юзеров.
        resp = api.get(f'/tours/{tour_id}/active_meshes/{active_mesh}')
        assert resp.status_code == 403

        # Описание задачи: Пробуем получить один меш тура
        # Параметр: с авторизацией
        # Ожидаемый результат: Любой авторизованный юзер, кроме забаненного может получить свой меш
        resp = api.get(f'/tours/{tour_id}/active_meshes/{active_mesh}', auth_as=user['email'])
        if user['banned']:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200


def test_raise_exception(api):
    """
    Плохие запросы
    """
    body = {'title': 'Добавим новый active_mesh', "actions": {"click": "6"}, "class": ["ad"],
            "hover": {"hide_cursor": True}, "type": "mesh", "name": "имя меша", "look": {"fill": 'rgba=[10,20,0,0]'}}

    # Описание задачи: Пробуем добавить меш
    # Параметр: Нет тура
    tour_id = 45
    active_mesh = 'ActivMesh0001'
    resp = api.put(f'/tours/{tour_id}/active_meshes/{active_mesh}', body=body)
    assert resp.status_code == 404
    assert resp.has_error('Tour not found.')

    # Описание задачи: Пробуем добавить меш
    # Параметр: Отсутствует параметр type
    body = {'title': 'Будет новый title', "actions": {"click": "9"}, "class": ["ad", "del"],
            "hover": {"hide_cursor": False}, "name": "Будет новое имя меша", "look": {"fill": 'rgba=[10,20,0,0]'}
            }
    tour_id = 3
    resp = api.put(f'/tours/{tour_id}/active_meshes/{active_mesh}', body=body, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Not enough active_mesh properties type.')

    # Описание задачи: Пробуем добавить меш
    # Параметр: пробуем удалить несуществующий меш
    tour_id = 3
    active_mesh = 'ActivMesh0001111'
    resp = api.delete(f'/tours/{tour_id}/active_meshes/{active_mesh}', auth_as='super@biganto.com')
    assert resp.status_code == 404
    assert resp.has_error('ActiveMesh ActivMesh0001111 not found.')


def test_del_active_mesh(api):
    active_mesh = 'ActivMesh0001'
    for user_id, user in USERS.items():
        tour_id = user_id

        # Описание задачи: Пробуем удалить меш
        # Параметр: Нет авторизации
        # Ожидаемый результат: Любой авторизованный юзер, кроме забаненного может удалить свой меш
        resp = api.delete(f'/tours/{tour_id}/active_meshes/{active_mesh}', auth_as=user['email'])
        if user['banned']:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 204
