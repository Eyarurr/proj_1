"""
https://gitlab.biganto.com/p/docs/wikis/models/Overlay
"""
import copy
import datetime

import pytest

from visual import create_app
from visual.core import db
from visual.models import User, TeamMember, AuthToken, Tour, Footage

USERS = {}
TOURS = {}

datasets = {'overlays': [
    {"id": 1, 'overlay': 'polyline',
     'body':
         {'type': 'polyline',
          'widget': {'pos': [1, 2, 3], 'coords': [1, 2, 3, 4], 'q': [0, 0, 0, 1], 'color': [0, 255, 0, 1]},
          'tooltip': None, 'actions': None, 'name': None,
          }},

    {"id": 2, 'overlay': 'polygon',
     'body': {'type': 'polygon',
              'widget': {'pos': [1, 2, 3], 'coords': [1.2, 2.2, 3.2, 4.2], 'faces': [1, 2], 'q': [1, 2, 3, 3],
                         'fill': [0, 255], 'fill_hover': [0, 255], 'border': None, }
              }},
    {"id": 3, 'overlay': 'ellipse',
     'body': {'type': 'ellipse',
              'widget':
                  {'pos': [['1', '2'], ['1', '8']], 'radiuses': [0, 0, 0, 1], 'q': [0, 0, 0, 1], 'fill': [0, 0, 0, 1],
                   'fill_hover': [0, 0, 0, 1], 'border': [0, 0, 0, 1], }, 'tooltip': None, 'actions': None,
              'name': None,
              }},

    {"id": 4, 'overlay': 'image',
     'body': {'type': 'image',
              'widget': {'pos': [1, 2, 3, 4, 5], 'q': [1, 2, 3, 4, 5], 'billboardmode': [1, 2, 3, 4, 5],
                         'perspective': [1, 2, 3, 4, 5],
                         'url': 'url', 'preset': [1, 2, 3, 4, 5], 'size': [1, 2, 3, 4, 5],
                         }
              }},

    {"id": 5, 'overlay': 'text',
     'body': {'type': 'text',
              'widget': {'pos': [1, 2, 3], 'q': [1, 2, 3], 'text': [1, 2, 3], 'billboardmode': [1, 2, 3],
                         'perspective': [1, 2, 3],
                         'font': [1, 2, 3], 'bar': [1, 2, 3], 'leg': [1, 2, 3]}, 'tooltip': None, 'actions': None,
              'name': None,

              }}
]}


def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3 - нормальные, 4 - удаленный и 5 - забаненный
    Создаем по одному туры каждому юзеру

    :return:
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        users = [
            User(id=1, name='anna', email='anna@biganto.com', email_confirmed=True, ),
            User(id=2, name='boris', email='boris@biganto.com', email_confirmed=True,
                 team_member=TeamMember(roles=['tours'])),
            User(id=3, name='super', email='super@biganto.com', email_confirmed=True),
            User(id=4, name='banned', email='banned@biganto.com', email_confirmed=True, banned=True, ),
            User(id=5, name='deleted', email='deleted@biganto.com', email_confirmed=True,
                 deleted=datetime.datetime.now() - datetime.timedelta(days=1)),
        ]
        for user in users:
            user.auth_tokens.append(
                AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30),
                          ip='0.0.0.0'))
            user.password_hash = user.hash_password('123') if user.id == 3 else None
            db.session.add(user)
            db.session.flush()
            tour = Tour(user_id=user.id, title='tour',
                        footage=Footage(user_id=user.id, _status='testing', type='real'),
                        )
            db.session.add(tour)

        USERS[user.id] = {k: getattr(user, k) for k in ("id", 'email', 'name', 'banned', 'deleted')}
        TOURS[tour.id] = {k: getattr(tour, k) for k in ("id", 'user_id', 'title')}

        db.session.commit()
        db.session.close()


@pytest.mark.access
def test_access_overlays(api):
    for user_id, user in USERS.items():
        tour_id = user_id
        # Попытка добавить оверлей без авторизации
        # Ожидаемый результат: 403 для всех
        resp = api.post(f'/tours/{tour_id}/virtual/overlays')
        assert resp.status_code == 403

        # Попытка получить оверлеи без авторизации
        # Ожидаемый результат: 403
        resp = api.get(f'/tours/{tour_id}/virtual/overlays')
        assert resp.status_code == 403

        # Попытка получить оверлей без авторизации
        # Ожидаемый результат: 403
        resp = api.get(f'/tours/{tour_id}/virtual/overlays/1')
        assert resp.status_code == 403


def test_post_overlays(api):
    """
    Добавить оверлей
    POST /tours/<tour_id>/virtual/overlays
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['overlays']:

            # Авторизованные юзеры пытаются добавить оверлей в свой тур
            # Ожидаемый результат: все авторизованные юзеры могут добавить себе все оверлеи
            # Забаненный юзер не может добавлять оверлей
            resp = api.post(f'/tours/{tour_id}/virtual/overlays', body=dataset['body'], auth_as=user['email'])
            if user['email'] != 'banned@biganto.com':
                assert resp.status_code == 200
            else:
                assert resp.status_code == 403


def test_get_overlays(api):
    """
    Получить оверлеи
    GET /tours/<tour_id>/virtual/overlays
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = user_id

        # Авторизованные юзеры пытаются получить свои оверлеи
        # Ожидаемый результат: все авторизованные юзеры, кроме забаненного могут получить все свои оверлеи
        resp = api.get(f'/tours/{tour_id}/virtual/overlays', auth_as=user['email'], )
        if user['email'] != 'banned@biganto.com':
            assert resp.status_code == 200
        else:
            assert resp.status_code == 403


def test_get_overlay(api):
    """
    Получим все оверлеи по одному в туре для каждого юзера
    GET /tours/<tour_id>/virtual/overlays/<overlay_id>
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        for overlay_id in range(1, len(datasets) + 1):
            tour_id = user_id

            # Авторизованные юзеры пытаются получить свой оверлей
            # Ожидаемый результат: все авторизованные юзеры, кроме забаненного могут получить свой оверлей
            resp = api.get(f'/tours/{tour_id}/virtual/overlays/{overlay_id}', auth_as=user['email'])
            if user['email'] != 'banned@biganto.com':
                assert resp.status_code == 200
            else:
                assert resp.status_code == 403


def test_put_overlay(api):
    """
    Изменить оверлей
    PUT /tours/<tour_id>/virtual/overlays/<overlay_id>
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['overlays']:
            name = dataset['body']['type'] + '_new name'
            dataset['body']['name'] = name
            overlay_id = dataset["id"]

            # Пробуем изменить оверлей
            # Ожидаемый результат: любой юзер, кроме забаненного может поменять оверлей
            resp = api.put(f'/tours/{tour_id}/virtual/overlays/{overlay_id}', body=dataset['body'], auth_as=user['email'])
            if user['email'] != 'banned@biganto.com':
                assert resp.status_code == 200
            else:
                assert resp.status_code == 403

            # Пробуем добавить оверлей
            # Ожидаемый результат: любой юзер, кроме забаненного может добавить оверлей
            resp = api.put(f'/tours/{tour_id}/virtual/overlays/{overlay_id + 100}',
                           body=dataset['body'], auth_as=user['email'], )
            if user['email'] != 'banned@biganto.com':
                assert resp.status_code == 200
            else:
                assert resp.status_code == 403


def test_del_overlay(api):
    """
    Удалить один оверлей
    DELETE /tours/<tour_id>/virtual/overlays/<overlay_id>
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        # Пробуем удалить оверлей
        # Ожидаемый результат: любой юзер, кроме забаненного может удалить оверлей
        resp = api.delete(f'/tours/{tour_id}/virtual/overlays/1', auth_as=user['email'])
        if user['email'] != 'banned@biganto.com':
            assert resp.status_code == 204
        else:
            assert resp.status_code == 403

@pytest.mark.bad_requests
def test_exception(api):
    """
    В теле запроса допущены ошибки данных
    """
    tour_id = 3
    overlay_id = '1000'
    # Получить несуществующий оверлей тура
    resp = api.get(f'/tours/{tour_id}/virtual/overlays/{overlay_id}', auth_as='super@biganto.com', )

    assert resp.status_code == 404
    assert resp.has_error(f'Overlay {overlay_id} not found.')

    # Указан неверный тип изменяемого оверлея
    # todo: неплохо бы сделать валидацию для type
    overlay_id = '20'
    simple_dataset = {
        'type': 'BED TYPE',
        'widget': {}
    }
    resp = api.put(f'/tours/{tour_id}/virtual/overlays/{overlay_id}', simple_dataset, auth_as='super@biganto.com', )
    assert resp.status_code == 200

    # Некорректное свойств
    for dataset in datasets['overlays']:
        dataset['body']['some_param'] = None
        overlay_id = dataset["id"] + 200
        resp = api.put(f'/tours/{tour_id}/virtual/overlays/{overlay_id}', body=dataset['body'], auth_as='super@biganto.com', )
        assert resp.status_code == 200
        assert resp.has_warning('Unknown input property some_param')

        # Некорректное свойство в widget
        # Ожидаемый результат: widget не проверяет доп свойство
        for dataset in datasets['overlays']:
            dataset['body']['widget']['some_param'] = [1, 2, 3]
        resp = api.put(f'/tours/{tour_id}/virtual/overlays/{dataset["id"] + 300}', body=dataset['body'], auth_as='super@biganto.com', )
        assert resp.status_code == 200

        # Отсутствует свойство type
        datasets_copy = copy.deepcopy(datasets['overlays'])
        for dataset in datasets_copy:
            del dataset['body']['type']
        resp = api.put(f'/tours/{tour_id}/virtual/overlays/{dataset["id"] + 220}', body=dataset['body'], auth_as='super@biganto.com', )
        assert resp.status_code == 400
        assert resp.has_error('Not enough overlay properties type.')

        # Отсутствует свойство widget
        datasets_copy = copy.deepcopy(datasets['overlays'])
        for dataset in datasets_copy:
            del dataset['body']['widget']
        resp = api.put(f'/tours/{tour_id}/virtual/overlays/{dataset["id"] + 220}', body=dataset['body'], auth_as='super@biganto.com')
        assert resp.status_code == 400
        assert resp.has_error('Not enough overlay properties widget.')

        # удалить не существующий оверлей
        tour_id = 3
        resp = api.delete(f'/tours/{tour_id}/virtual/overlays/1000', auth_as='super@biganto.com', )
        assert resp.status_code == 404
        assert resp.has_error('Overlay 1000 not found.')
