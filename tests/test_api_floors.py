"""
Ссылка на wiki
api
https://gitlab.biganto.com/p/docs/wikis/api3/floors
Floor
https://gitlab.biganto.com/p/docs/wikis/models/Floor
"""
import os
import json
import datetime
import pytest
from sqlalchemy.orm.attributes import flag_modified

from tests.common import set_flow
from visual import create_app
from visual.core import db
from visual.models import User, Footage, Tour, TeamMember, AuthToken
from visual.util import unzip_footage_tour

from .conftest import SRC_DIR

with open(os.path.join(SRC_DIR, 'meta.json')) as fm:
    meta = json.load(fm)

datasets = {
    'put_floor': [
    {'id': 1, 'title': 'put_floor',
     'description': 'Попытка добавить floor',
     'body': {'title': 'Первый этаж', 'big@flow': 'TOKEN/256x256.jpg', 'small@resize': [100, 100],
              'big@resize': [300, 300], 'scale': 1.5, 'offset': [20, 20],
              },
     },
    {'id': 2, 'title': 'put_floor',
     'description': 'Попытка изменить floor',
     'body': {'title': 'Первый этаж измененный', 'big@flow': None, 'small@resize': [100, 100], 'big@resize': [300, 300],
              'scale': None, 'offset': None,
              },
     },
],
    'put_floor_add': [
    {'id': 1, 'title': 'put_floor',
     'description': 'Попытка добавить floor',
     'body': {'title': 'Новый этаж', 'big@flow': 'TOKEN/256x256.jpg', 'small@resize': [100, 100],
              'big@resize': [300, 300], 'scale': 1.5, 'offset': [20, 20],
              },
     },
],
    'put_floors': [
        {'id': 1, 'title': 'put_floors',
         'body': {
             1: {'title': 'Первый этаж', 'big@flow': 'TOKEN/256x256.jpg', 'small@resize': [100, 100],
                 'big@resize': [300, 300], 'scale': 1.5, 'offset': [20, 20],
                 },
             2: {'title': 'Второй этаж', 'big@flow': 'TOKEN/256x256.jpg', 'small@resize': [100, 100],
                 'big@resize': [300, 300], 'scale': 1.5, 'offset': [20, 20],
                 },
             3: {'title': 'Второй этаж', 'big@flow': 'TOKEN/256x256.jpg', 'small@resize': [100, 100],
                 'big@resize': [300, 300], 'scale': 1.5, 'offset': [20, 20],
                 },
         }
         },
        {'id': 2, 'title': 'put_floors',
         'body': {
             1: {'title': 'Первый этаж измененный', 'big@flow': None, 'small@resize': [100, 100],
                 'big@resize': [300, 300], 'scale': None, 'offset': None,
                 },
             2: {'title': 'Второй этаж измененный', 'big@flow': None, 'small@resize': [100, 100],
                 'big@resize': [300, 300], 'scale': None, 'offset': None,
                 },
             3: {'title': 'Второй этаж измененный', 'big@flow': None, 'small@resize': [100, 100],
                 'big@resize': [300, 300], 'scale': None, 'offset': None,
                 },
         }
         }]
}

USERS = {}
TOURS = {}
FOOTAGES = {}


def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3 - нормальные, 4 - забаненный и 5 - удалённый
    Создаем по одному туру и съемке каждому юзеру.
    Для каждой съемки создадим каталог для ассетов
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
                        footage=Footage(user_id=user.id, _status='testing', type='real', meta=meta))
            db.session.add(tour)
            db.session.flush()

            tour.mkdir()
            tour.footage.mkdir()
            path = os.path.join(SRC_DIR, 'tours', 'tour-20335.zip')
            unzip_footage_tour(path, footage=tour.footage, tour=tour)


            # Добавим в скайбокса 14 floor равный 3
            tour.footage.meta['skyboxes']['14']['floor'] = 3
            flag_modified(tour.footage, 'meta')
            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            FOOTAGES[tour.footage.id] = {k: getattr(tour.footage, k) for k in ('id', 'user_id', 'type')}
            FOOTAGES[tour.footage.id].update({'in_files': tour.footage.in_files()})
        #

        db.session.commit()
        db.session.close()


@pytest.mark.access
def test_access(api):
    footage_id = 1
    floor_id = 1
    # Описание: Пытаемся добавить и изменить этаж
    # Параметры: Без токена авторизации
    # Ожидаемый результат: 403
    resp = api.put(f'/footages/{footage_id}/virtual/floors/{floor_id}')
    assert resp.status_code == 403

    # Описание: Пытаемся добавить и изменить список этажей
    # Параметры: Без токена авторизации
    # Ожидаемый результат: 403
    resp = api.put(f'/footages/{footage_id}/virtual/floors')
    assert resp.status_code == 403

    # Описание: Пытаемся удалить этаж.
    # Параметры: Без токена авторизации
    # Ожидаемый результат: 403
    resp = api.delete(f'/footages/{footage_id}/virtual/floors/{floor_id}')
    assert resp.status_code == 403


def test_put_floor(api):
    """
    Сохранить этаж
    PUT /footages/<footage_id>/virtual/floors/<floor_id>
    тело
    {
    'big@flow': 'TOKEN/filename',  // null здесь сотрёт планировку существующего этажа
    'big@resize': [int, int],  // До какого размера ресайзить большую планировку
    'small@resize': [int, int],  // До какого размера ресайзить маленькую планировку
    'title': str,
    'offset': [float, float],
    'scale': float,
    'big': str,     // Можно указать URL картинки напрямую. Вместе со свойством big@flow работает непредсказуемо
    'small': str
    }

    """
    for user_id, user in USERS.items():
        footage_id = user_id
        floor_id = 2
        for dataset in datasets['put_floor']:
            set_flow({'TOKEN': ['src/256x256.jpg']})
            # Описание: Пытаемся добавить и изменить этаж
            # Параметры: С токеном авторизации
            # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может добавить и изменить свой этаж
            resp = api.put(f'/footages/{footage_id}/virtual/floors/{floor_id}', auth_as=user['email'], body=dataset['body'])
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 200
                list_dir = os.listdir(os.path.join(FOOTAGES[footage_id]['in_files'], 'maps'))
                # Проверим, что добавляются файлы
                if dataset['id'] == 1:
                    assert len(list_dir) != 0

                # Проверим, что удаляются файлы
                else:
                    assert len(list_dir) == 0


def test_put_floors(api):
    for user_id, user in USERS.items():
        footage_id = user_id
        for dataset in datasets['put_floors']:
            set_flow({'TOKEN': ['src/256x256.jpg']})

            # Описание: Пытаемся добавить и изменить список этажей
            # Параметры: С токеном авторизации
            # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может добавить и изменить свои
            # этажи списком
            resp = api.put(f'/footages/{footage_id}/virtual/floors', auth_as=user['email'], body=dataset['body'])
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 200
                list_dir = os.listdir(os.path.join(FOOTAGES[footage_id]['in_files'], 'maps'))
                # Проверим, что добавляются файлы
                if dataset['id'] == 1:
                    assert len(list_dir) != 0
                # Проверим, что удаляются файлы
                else:
                    assert len(list_dir) == 0


def test_exceptions(api):
    """
    Вызываем исключения
    :param api:
    :return:
    """
    user_id = 3
    user = USERS[user_id]
    footage_id = user_id
    floor_id = 1
    # Первый этаж не может быть удален
    resp = api.delete(f'/footages/{footage_id}/virtual/floors/{floor_id}', auth_as=user['email'], _debug=True)
    assert resp.status_code == 404
    assert resp.has_error(f'Floor {floor_id} cannot be deleted')


    floor_id = 3
    # Этаж не может быть удален, если хотя бы в одном скайбоксе он присутствует.
    resp = api.delete(f'/footages/{footage_id}/virtual/floors/{floor_id}', auth_as=user['email'], _debug=True)
    assert resp.status_code == 404
    assert resp.has_error(f'Floor {floor_id} cannot be deleted')

    floor_id = 10
    # Указан несущестующий этаж
    resp = api.delete(f'/footages/{footage_id}/virtual/floors/{floor_id}', auth_as=user['email'])
    assert resp.status_code == 404
    assert resp.has_error(f'Floor {floor_id} not found.')


def test_delete_floor(api):
    """
    Удалить этаж
    DELETE /footages/<footage_id>/virtual/floors/<floor_id>
    """
    for user_id, user in USERS.items():
        footage_id = user_id
        floor_id = 2

        # Описание: Пытаемся удалить этаж.
        # Параметры: С токеном авторизации
        # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может удалить этаж
        resp = api.delete(f'/footages/{footage_id}/virtual/floors/{floor_id}', auth_as=user['email'])
        if user['banned']:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 204


def test_delete_floor_minimap(api):
    """
    Удаляет картинки планировок этажа
    DELETE /footages/<int:footage_id>/floors/<int:floor_id>/minimap
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        footage_id = user_id
        floor_id = 1
        for dataset in datasets['put_floor']:
            set_flow({'TOKEN': ['src/256x256.jpg']})
            if dataset['id'] != 1:
                continue
            # Добавим планировки в этаж
            api.put(f'/footages/{footage_id}/virtual/floors/{floor_id}', auth_as=user['email'],
                           body=dataset['body'])

            # Описание: Пытаемся удалить планировки этажа.
            # Параметры: С токеном авторизации
            # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может удалить планировки этажа
            resp = api.delete(f'/footages/{footage_id}/floors/{floor_id}/minimap', auth_as=user['email'],
                            _debug=True)
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 204