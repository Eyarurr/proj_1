"""
todo Загрузка ассетов через upload-slot не тестировалось
 "assets": "upload-slot@upload1.biganto.com/SLUT"
"""
import datetime
import json
import os
import shutil

import pytest

from visual import create_app
from visual.core import db
from visual.models import User, Tour, Footage, TeamMember, AuthToken
from visual.util import unzip_footage_tour
from .conftest import SRC_DIR

with open(os.path.join(SRC_DIR, 'meta.json')) as fm:
    meta = json.load(fm)

datasets = {
    'put_footage': [
        {'id': 1,
         'body': {
             'status': 'testing',
             'meta.skyboxes.5.pos': [1, 2, 3]
         },
         'query_string': {
             'fields': 'default'}
         },
        {'id': 2,
         'body': {
             'status': 'loading',
         },
         'query_string': {
             'fields': 'id,status'}
         },
        {'id': 3,
         'body': {
             'meta': meta,
         },
         'query_string': {
             'fields': 'id,meta.skyboxes.5.pos'}
         },
    ],
    'get_footage': [
        {'id': 1,
         'query_string': {
             'fields': 'id,created,updated,user_id,type,status,cnt_skyboxes,meta,meta.skyboxes.5'}
         },
        {'id': 2,
         'query_string': {
             'fields': 'default'},
         'desc_default': 'id, created, updated, user_id, type, status'.strip()
         },
    ],
    'get_files': [
        {'id': 1,
         'query_string': {}
         },
        {'id': 2,
         'query_string': {'dir': '256',
                          'fields': 'default'},
         },
        {'id': 3,
         'query_string': {'dir': '300',
                          'fields': 'default'},
         },

    ],
    'bad_request': [
        {'id': 1,
         'query_string': {'dir': '300',
                          'fields': 'default'},
         },

    ],
}

USERS = {}
TOURS = {}
FOOTAGES = {}


def setup_module():
    """
    Создадим пять юзеров. Каждому юзеру создадим по одному туру и съемке. В каждую съемку распакуем ассеты
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
            FOOTAGES[tour.id] = {k: getattr(tour.footage, k) for k in ('id', 'user_id', 'meta')}
            FOOTAGES[tour.id]['in_files'] = tour.footage.in_files()

            if user.id  == 1:
                file_upload = app.config['FLOW_UPLOAD_TMP_DIR']
                dst_dir = os.path.join(file_upload, 'TOKEN')
                if os.path.exists(dst_dir):
                    shutil.rmtree(dst_dir)
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copytree(tour.footage.in_files(), dst_dir, dirs_exist_ok=True)

        db.session.commit()
        db.session.execute("""SELECT setval('tours_id_seq', 100)""")
        db.session.execute("""SELECT setval('footages_id_seq', 100)""")


def test_put_footage(api):
    """
    Сохранить свойства съёмки
    PUT /footages/<footage_id>

    GET-параметры:
    fields. Какие свойства включить в ответ
    Тело запроса:
    {
        'status': str,
        'meta': { /* можно записать всю мету съёмки */ },
        'meta.skyboxes.5.pos': [0,0,0],  // а можно только какой-то элемент по селектору
        'assets': location    // Можно сразу загрузить ассеты
    }
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        footage_id = user_id
        for dataset in datasets['put_footage']:

            #  Попытка сохранить свойства съёмки. Без авторизации
            #  Ожидаемый результат: 403
            resp = api.put(f'/footages/{footage_id}', query_string=dataset['query_string'], body=dataset['body'])
            assert resp.status_code == 403

            #  Попытка сохранить свойства съёмки с авторизацией всеми юзерами, по своим съемкам.
            #  Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может изменить свою съемку
            resp = api.put(f'/footages/{footage_id}', auth_as=user['email'], query_string=dataset['query_string'], body=dataset['body'])
            if not user['banned']:
                assert resp.status_code == 200
            else:
                assert resp.status_code == 400 or resp.status_code == 403


def test_get_footage(api):
    """
    GET /footages/<footage_id>

    GET-параметры:
    default, id, created, updated, user_id, type, status, cnt_skyboxes,meta, meta.selector
    default = id, created, updated, user_id, type, status.
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        footage_id = user_id
        for dataset in datasets['get_footage']:

            #  Попытка получить съемки. Без авторизации
            #  Ожидаемый результат: Можно получить свойства любой съемки, только не забаненного и удаленного юзера
            resp = api.get(f'/footages/{footage_id}', query_string=dataset['query_string'])
            if user['email'] not in ('banned@biganto.com', 'deleted@biganto.com'):
                assert resp.status_code == 200
            else:
                assert resp.status_code == 403

            #  Попытка получить съемки с авторизацией
            #  Ожидаемый результат: Любой не авторизированный юзер, кроме забаненного может получить свойство
            #  своей съемки
            resp = api.get(f'/footages/{footage_id}', auth_as=user['email'], query_string=dataset['query_string'])
            if not user['banned']:
                assert resp.status_code == 200
                # Проверяем, что возвращаются заказанные поля
                if dataset['query_string']['fields'] == 'default':
                    assert set(map(lambda x: x.strip(), str(dataset['desc_default']).split(','))) \
                           == set(resp.result)
                else:
                    assert set(dataset['query_string']['fields'].split(',')) == set(resp.result)
            else:
                assert resp.status_code == 400 or resp.status_code == 403


def test_get_files_footage(api):
    """
    GET /footages/<id>/files
    GET-параметры:
    {'dir': из какой поддиректории,
    ?fields - список из name, fsize, ctime, isize (default: name)
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        footage_id = user_id
        for dataset in datasets['get_files']:
            if dataset['id'] < 3:
                # Попытка получить файлы съемки без авторизации.
                # Ожидаемый результат: Получить файлы съемок можно у любой съемки кроме съемок удаленного
                # и забаненного юзера
                resp = api.get(f'/footages/{footage_id}/files', query_string=dataset['query_string'])

                if user['email'] not in ('banned@biganto.com', 'deleted@biganto.com'):
                    assert resp.status_code == 200
                else:
                    assert resp.status_code == 403

                # Попытка получить файлы своей съемки с авторизацией.
                # Ожидаемый результат: Получить файлы съемок может любой авторизованный юзер кроме забаненного
                resp = api.get(f'/footages/{footage_id}/files', auth_as=user['email'], query_string=dataset['query_string'])
                if not user['banned']:
                    assert resp.status_code == 200
                else:
                    assert resp.status_code == 403

@pytest.mark.bad_requests
def test_exception(api):
    """
    Плохие запросы
    :param api:
    """
    user_id = 1
    user = USERS[user_id]
    footage_id = user_id
    for dataset in datasets['bad_request']:
        # Попытка получить файлы своей съемки с авторизацией.
        # Параметры: Не существующий каталог
        # Ожидаемый результат: 400
        resp = api.get(f'/footages/{footage_id}/files', auth_as=user['email'], query_string=dataset['query_string'])
        if not user['banned']:
            assert resp.status_code == 400
            assert resp.has_error('Directory 300 does not exist.')

    # GET /footages/id

    # Перед тестами сделаем снимок с footage.meta
    query_string = {'fields': 'meta'}
    check_resp = api.get(f'/footages/1', auth_as='anna@biganto.com', query_string=query_string)
    meta_before = check_resp.result
    
    # После всех тестов footage.meta не должна быть измененной
    check_resp = api.get(f'/footages/1', auth_as='anna@biganto.com', query_string=query_string)
    meta_after = check_resp.result
    assert meta_before == meta_after

    # DELETE /footages
    # Параметры: не указан селектор
    resp = api.delete(f'/footages/1/meta', auth_as='anna@biganto.com')
    assert resp.status_code == 404
    assert resp.has_error('The requested URL was not found on the server')

    # Параметры: nonexistent - не существует
    resp = api.delete(f'/footages/1/meta.nonexistent', auth_as='anna@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Malformed nonexistent value. ')

    # Параметры: start.q - существует q1 - не существует
    resp = api.delete(f'/footages/1/meta.skyboxes.1.q1', auth_as='anna@biganto.com', )
    assert resp.status_code == 400
    assert resp.has_error('Malformed q1 value. ')

    # Параметры: skyboxes.1.q и skyboxes.1.pos- существуют
    resp = api.delete(f'/footages/1/meta.skyboxes.1.q.pos', auth_as='anna@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Malformed pos value. ')

    # Параметры: skyboxes.1.q - существует q1 - не существует
    resp = api.delete(f'/footages/1/meta.skyboxes.1.q.q1', auth_as='anna@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Malformed q1 value. ')

    # PUT /footages
    user_id = 1
    user = USERS[user_id]

    # неверное значение для type
    body = {'type': 'some_type'}
    resp = api.post(f'/footages', body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error("Malformed type some_type")

    # неверное значение для type.
    body = {'type': 123}
    resp = api.post(f'/footages', body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error(" Malformed type 123")

    # неверное значение для type.
    body = {'type': ''}
    resp = api.post(f'/footages', body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error(" Malformed type")

    # неверное значение для type.
    body = {'type': ''}
    resp = api.post(f'/footages', body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error(" Malformed type")

    # неверное значение для type.
    body = {'status': ''}
    resp = api.post(f'/footages', body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error("Malformed status")

    # неверное значение для type.
    body = {'user_id': 100}
    resp = api.post(f'/footages', body, auth_as=user['email'])
    assert resp.status_code == 404
    assert resp.has_error("User not found.")

    # нет юзера с таким ID
    body = {'user_id': 100}
    resp = api.post(f'/footages', body, auth_as=user['email'])
    assert resp.status_code == 404
    assert resp.has_error("User not found.")

    # user_id не число
    body = {'user_id': 'str'}
    resp = api.post(f'/footages', body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error("value is not a valid integer")
    
    # assets неверный формат
    body = {'assets': 'str'}
    resp = api.post(f'/footages', body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error("Malformed assets value.")

    # assets неверный формат
    body = {'assets': 'flow@TOKEN/some_file'}
    resp = api.post(f'/footages', body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error("Source file TOKEN/some_file not found for assets.")

def test_delete_meta_selector(api):
    """
    DELETE /tours/<tour_id>/meta.<selector>
    Проверяем удаление ключей в footage.meta по селектору
    Для проверки правильности удаления используется дополнительный API метод GET /footages/<footage_id>
    """
    for user_id, user in USERS.items():
        footage_id = user_id

        # Описание: Пытаемся удалить свойства в footage.meta по селектору
        # Параметры: С токеном авторизации.
        # Ожидаемый результат: 204 Любой юзер кроме забаненного может удалить свойства tour.meta по селектору
        # Доказательств: при помощи GET запроса запрашиваем 'selector' до запроса на удаление и после

        # SET 1
        # Первый уровень вложенности
        selector = 'meta.floors'
        query_string = {'fields': f'{selector}'}
        check_resp = api.get(f'/footages/{footage_id}', auth_as=user['email'], query_string=query_string)
        # Проверим, что селектор существовал
        if not user['banned']:
            assert check_resp.status_code == 200
            assert selector in check_resp.result

        resp = api.delete(f'/footages/{footage_id}/{selector}', auth_as=user['email'])
        check_resp = api.get(f'/footages/{footage_id}', auth_as=user['email'], query_string=query_string,  _debug=True)

        # Проверяем, что селектор удален и что повторный GET запрос к съемке не вернет этот селектор
        if not user['banned']:
            assert check_resp.has_warning(f'Unknown field {selector}')
            assert selector not in check_resp.result
        else:
            assert resp.status_code == 403

        # SET 2
        # Проверим, что удаляется двойная вложенность селекторов и не удаляется промежуточные селекторы
        selector = 'meta.skyboxes.2'
        query_string = {'fields': f'{selector}'}
        check_resp = api.get(f'/footages/{footage_id}', auth_as=user['email'], query_string=query_string)
        # Проверим, что селектор существовал
        if not user['banned']:
            assert check_resp.status_code == 200
            assert selector in check_resp.result
        else:
            assert check_resp.status_code == 403

        resp = api.delete(f'/footages/{footage_id}/{selector}', auth_as=user['email'])
        if not user['banned']:
            assert resp.status_code == 204
        else:
            assert resp.status_code == 403

        # Проверяем, что повторный GET запрос к съемке не вернет этот селектор
        check_resp = api.get(f'/footages/{footage_id}', auth_as=user['email'], query_string=query_string)
        if not user['banned']:
            assert check_resp.has_warning(f'Unknown field {selector}')
            assert selector not in check_resp.result

        # Проверяем GET запрос к промежуточному селектору
        selector = 'meta.skyboxes'
        query_string = {'fields': f'{selector}'}
        check_resp = api.get(f'/footages/{footage_id}', auth_as=user['email'], query_string=query_string)
        if not user['banned']:
            assert check_resp.status_code == 200
            assert selector in check_resp.result

        # SET 3
        # Попытка удалить тройную вложенность селекторов. Селектор должен удалится, промежуточные - нет
        selector = 'meta.skyboxes.1.pos'
        query_string = {'fields': f'{selector}'}
        check_resp = api.get(f'/footages/{footage_id}', auth_as=user['email'], query_string=query_string)
        # Проверяем, что селектор существовал
        if not user['banned']:
            assert check_resp.status_code == 200
            assert selector in check_resp.result

        resp = api.delete(f'/footages/{footage_id}/{selector}', auth_as=user['email'])
        if not user['banned']:
            assert resp.status_code == 204
        else:
            assert resp.status_code == 403

        # Проверяем, что повторный GET запрос к съемке не вернет этот селектор
        check_resp = api.get(f'/footages/{footage_id}', auth_as=user['email'], query_string=query_string)
        if not user['banned']:
            assert resp.status_code == 204
            assert check_resp.has_warning(f'Unknown field {selector}')
            assert selector not in check_resp.result

        # Проверим что промежуточные не удалились
        selectors = ['meta.skyboxes.1', 'meta.skyboxes', ]
        for selector in selectors:
            query_string = {'fields': f'{selector}'}
            check_resp = api.get(f'/footages/{footage_id}', auth_as=user['email'], query_string=query_string)
            if not user['banned']:
                assert check_resp.status_code == 200
                assert selector in check_resp.result


def test_post_footage(api):
    """
    Создать съемку
    PUT /footages

    {
    "user_id": int,
    "type": str,
    "status": str(default testing),
    "meta": object={},
    "assets": "flow@TOKEN/*"}
    }
    """
    for user_id, user in USERS.items():
        # Добавим съемку без параметров
        body = {}
        resp = api.post(f'/footages', body, auth_as=user['email'])
        if not user['banned'] and not user['deleted'] :
            assert resp.status_code == 200
            assert resp.result['id'] not in FOOTAGES
            resp = api.get(f'/footages/{resp.result["id"]}', auth_as=user['email'])
            assert resp.status_code == 200

        # Добавим съемку с параметрами
        body = {'status': 'testing', 'type': 'virtual'}
        resp = api.post(f'/footages', body, auth_as=user['email'])
        if not user['banned'] and not user['deleted'] :
            assert resp.status_code == 200
            assert resp.result['id'] not in FOOTAGES

            # проверка, что съемка создалась
            resp = api.get(f'/footages/{resp.result["id"]}', auth_as=user['email'])
            assert resp.status_code == 200
            assert resp.result['type'] == body['type']
            assert resp.result['status'] == body['status']
        
        # Добавим съемку другому юзеру
        body.setdefault('user_id', 1)
        resp = api.post(f'/footages', body, auth_as=user['email'])
        if user_id == 2 or body['user_id'] == user_id and not  user['banned'] and user['banned']:
            assert resp.status_code == 200
            assert resp.result['id'] not in FOOTAGES
            # проверка, что съемка создалась
            resp = api.get(f'/footages/{resp.result["id"]}', auth_as=user['email'])
            assert resp.status_code == 200
            assert resp.result['type'] == body['type']
            assert resp.result['status'] == body['status']
            assert resp.result['user_id'] == body['user_id']
        body.pop('user_id')

        # Создадим съемку и добавим файлы ассетов
        # проверить нет возможности
        body.setdefault('assets','flow@TOKEN/*')
        body['meta'] = meta
        resp = api.post(f'/footages', body, auth_as=user['email'])
        if not user['banned'] and user['banned']:
            assert resp.status_code == 200
            resp = api.get(f'/footages/{resp.result["id"]}', auth_as=user['email'])
            assert resp.status_code == 200

        # Создадим съемку и добавим файлы ассетов
        # проверить нет возможности
        body.pop('assets')
        body.pop('meta')
        body['tours_id'] = [1]
        resp = api.post(f'/footages', body, auth_as=user['email'])
        if user_id == body['tours_id'] or user_id == 2 or not user['banned'] and user['banned']:
            assert resp.status_code == 200
            resp = api.get(f'/footages/{resp.result["id"]}', auth_as=user['email'])
            assert resp.status_code == 200
