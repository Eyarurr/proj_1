"""
Тесты методов API Умной Стройки: задачи.
"""
import pytest
import datetime

from visual import create_app
from visual.core import db
from visual.models import User, AuthToken, Footage, Tour

# Сторадж для передачи данных между тестами
MEMO = {
    # {email: User, ...}
    'users': {},
    # {id: Tour, ...}
    'tours': {},
    # {id: TourTags, ...}
    'tags': {}
}


def create_users():
    """
    Создаёт юзеров:
    1. anna@biganto.com.
    2. boris@biganto.com.

    Возвращает словарь {email: {'id': User.id, 'name': User.name, 'email': User.email}, ...}
    """
    users = [
        {'id': 1, 'email': 'anna@biganto.com', 'name': 'Anna'},
        {'id': 2, 'email': 'boris@biganto.com', 'name': 'Boris'},
    ]
    result = {}
    for kwargs in users:
        user = User(email_confirmed=True, **kwargs)
        user.auth_tokens.append(
            AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30), ip='0.0.0.0')
        )
        db.session.add(user)
        result[user.email] = {'id': user.id, 'email': user.email, 'name': user.name}

    return result


def setup_module():
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.expire_on_commit = False

        MEMO['users'] = create_users()

        tours = [
            # Хорошие.
            {'id': 1, 'user_id': 1, 'type': 'virtual', 'status': 'published'},
            {'id': 2, 'user_id': 1, 'type': 'virtual', 'status': 'published'},
            {'id': 3, 'user_id': 1, 'type': 'virtual', 'status': 'published'},
            {'id': 4, 'user_id': 1, 'type': 'virtual', 'status': 'published'},
            {'id': 5, 'user_id': 1, 'type': 'virtual', 'status': 'published'},

            {'id': 21, 'user_id': 2, 'type': 'real', 'status': 'testing'},
            {'id': 22, 'user_id': 2, 'type': 'real', 'status': 'testing'},
            {'id': 23, 'user_id': 2, 'type': 'real', 'status': 'testing'},
            {'id': 24, 'user_id': 2, 'type': 'real', 'status': 'testing'},
            {'id': 25, 'user_id': 2, 'type': 'real', 'status': 'testing'},

        ]

        for src in tours:
            footage = Footage(id=src['id'], user_id=src['user_id'], type=src['type'], _status=src['status'])
            tour = Tour(id=src['id'], footage=footage, user_id=src['user_id'])
            if 'meta' in src:
                tour.meta = src['meta']
            db.session.add(footage)
            db.session.add(tour)

        db.session.commit()


@pytest.mark.bad_requests
def test_post_user_tags_bad(api):
    """
    POST /my/<id>/tags
    """
    # [(auth_as, body), ...]
    bodies = [
        ('anna@biganto.com', 'Я сделан из мяса'),  # Тело запроса — не объект
        ('anna@biganto.com', {}),                  # Пустое тело запроса
        ('boris@biganto.com', {'foo': 'bar'}),     # Отсутствует name
        ('boris@biganto.com', {'name': None}),     # Плохой тип имени
        ('boris@biganto.com', {'name': False}),    # Плохой тип имени
        ('boris@biganto.com', {'name': ''}),       # Пустое имя
        ('boris@biganto.com', {'name': '     '}),  # Пустое имя
        ('boris@biganto.com', {'name': 'Гегель', 'display_dict': 1}),  #
    ]
    for auth_as, body in bodies:
        resp = api.post(f'/my/tags', body, auth_as=auth_as)
        assert resp.status_code == 400, f'{auth_as} - {body} - {resp.object}'


@pytest.mark.access
def test_post_user_tags_access(api):
    # [(auth_as, body), ...]
    bodies = [
        (None, {'name': 'Площадь'}),  # Без авторизации
    ]
    for auth_as, body in bodies:
        resp = api.post(f'/my/tags', body, auth_as=auth_as)
        assert resp.status_code in (404, 403), f'{auth_as} - {body} - {resp.object}'


def test_post_user_tags_good(api):
    """
    POST /my/tags
    Создаёт 4 тега:
    id | user  | name
    ---+-------+---------
    1  | anna  | Яркость
    2  | anna  | Скорость
    3  | anna  | Размах
    4  | boris | Размах
    5  | boris | Двамах
    """
    # [(auth_as, body), ...]
    bodies = [
        ('anna@biganto.com', {'name': 'area'}),
        ('anna@biganto.com', {'name': '  price  '},),
        ('anna@biganto.com', {'name': 'type'},),
        ('boris@biganto.com', {'name': 'type'}),
        ('boris@biganto.com', {'name': 'metro', 'crm_key': 'something', 'prefix': 'перед', 'suffix': 'зад', 'display_dict': {'foo': 'bar'}}),
    ]
    for auth_as, body in bodies:
        resp = api.post(f'/my/tags', body, auth_as=auth_as)
        assert resp.status_code == 200, f'{auth_as} - {body} - {resp.object}'
        assert resp.result
        assert 'id' in resp.result
        assert resp.result['name'] == body['name'].strip()
        MEMO['tags'][resp.result['id']] = resp.result

    # На посошок проверим, что второй тег с таким же именем создать оно не даст
    resp = api.post(f'/my/tags', {'name': 'price'}, auth_as='anna@biganto.com')
    assert resp.status_code == 400, f'anna@biganto.com - {{name: "Скорость"}} - {resp.object}'


@pytest.mark.bad_requests
def test_put_user_tags_bad(api):
    # [(auth_as, tag_id, body), ...]
    bodies = [
        (None, 1, {'name': 'foo'}),  # Без авторизации
        ('anna@biganto.com', 4, {'name': 'foo'}),  # Чужой тег
        ('anna@biganto.com', 1, 'Я не объект'),  # Тело - не объект
        ('anna@biganto.com', 1, {'name': None}),  # Name пытаются удалить
        ('anna@biganto.com', 1, {'name': ''}),  # Name пустой
        ('anna@biganto.com', 1, {'name': '  \n  '}),  # Name пустой
        ('anna@biganto.com', 1, {'name': '\t type \n '}),  # Такой уже есть (id=3)
    ]
    for auth_as, tag_id, body in bodies:
        resp = api.put(f'/my/tags/{tag_id}', body, auth_as=auth_as)
        assert resp.status_code in (400, 404, 403), f'{auth_as} - {body} - {resp.object}'


def test_put_user_tags_good(api):
    """
    PUT /my/tags/<id>
    Создаёт 3 тега:
    id | user  | name
    ---+-------+---------
    1  | anna  | Яркость
    2  | anna  | Скорость
    3  | anna  | Размах
    4  | boris | Размах
    """
    # [(auth_as, tag_id, body), ...]
    bodies = [
        ('boris@biganto.com', 4, {'name': '  typetype\n  '}),
        ('boris@biganto.com', 4, {'label': 'Метка', 'prefix': '<', 'suffix': '>', 'crm_key': 'blabla', 'display_dict': {'1': 'one', '2': 'two'}}),
    ]
    for auth_as, tag_id, body in bodies:
        resp = api.put(f'/my/tags/{tag_id}', body, auth_as=auth_as)
        assert resp.status_code == 200, f'{auth_as} - {body} - {resp.object}'
        assert resp.result
        assert 'id' in resp.result
        if 'name' in 'body':
            assert resp.result['name'] == body['name'].strip()
        assert resp.result.get('prefix') == body.get('prefix')
        assert resp.result.get('suffix') == body.get('suffix')
        assert resp.result.get('crm_key') == body.get('crm_key')
        assert resp.result.get('display_dict') == body.get('display_dict')


def test_get_user_tag_good(api):
    """
    GET /my/tags
    """
    resp = api.get(f'/my/tags/1', auth_as='anna@biganto.com')
    assert resp.status_code == 200, resp.object
    assert resp.result
    assert resp.result['id'] == 1
    assert resp.result['name'] == MEMO['tags'][1]['name']


def test_get_user_tags_good(api):
    """
    GET /my/tags
    """
    resp = api.get(f'/my/tags', auth_as='anna@biganto.com')
    assert resp.status_code == 200, resp.object
    assert resp.result
    assert type(resp.result) is list
    assert len(resp.result) == 3


@pytest.mark.bad_requests
def test_delete_user_tag_bad(api):
    """
    DELETE /my/tags/<id>
    """
    # (auth_as, tag_id)
    bodies = [
        ('boris@biganto.com', 1),  # Чужой
        ('anna@biganto.com', 100000),  # Несуществущий
    ]
    for auth_as, tag_id in bodies:
        resp = api.delete(f'/my/tags/{tag_id}', auth_as=auth_as)
        assert resp.status_code in (400, 404, 403), f'{auth_as} - {resp.object}'


def test_delete_user_tag_good(api):
    """
    DELETE /my/tags/<id>
    """
    resp = api.delete(f'/my/tags/3', auth_as='anna@biganto.com')
    assert resp.status_code == 204, resp.object

    # Проверяем, что тега больше нет
    resp = api.get(f'/my/tags/3', auth_as='anna@biganto.com')
    assert resp.status_code == 404, resp.object
