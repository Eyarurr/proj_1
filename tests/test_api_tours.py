"""
https://gitlab.biganto.com/p/docs/wikis/api3/tours
"""
import datauri
import datetime
import json
import os
import shutil

import pytest

from tests.common import set_flow
from visual import create_app
from visual.core import db, redis
from visual.models import User, TeamMember, AuthToken, Tour, Footage, Folder, UserProduct
from visual.util import unzip_footage_tour
from .conftest import SRC_DIR
from tests.common import create_tours_footages_various_types
from visual.api3.common import delete_key_dict

with open(os.path.join(SRC_DIR, 'meta.json')) as fm:
    meta1 = json.load(fm)


datasets = {
    'post_tour': [
        {'id': 1, 'title': 'post_tour',
         'body': {'title': 'create_tour_for_yourself', 'footage_id': 1}},
        {'id': 2, 'title': 'post_tour',
         'body': {'title': 'create_tour_for_yourself',
                  'footage': {'type': 'virtual', 'status': 'testing',
                              'meta': {'some-key': 'some_val'}}}},
        {'id': 3, 'title': 'post_tour',
         'body': {
             'title': 'create_tour_for_yourself', 'hidden': True,
             'footage': {'type': 'virtual', 'status': 'published', 'meta': {}}}},
        {'id': 4, 'title': 'post_tour',
         'body': {'title': 'create_tour_other_user', 'user_id': 1, 'gallery_user': True, 'footage_id': 1}},
        {'id': 5, 'title': 'create_tour_other_user',
         'body': {
             'meta': {'some_key': 'some_val'},
             'title': 'create_tour_other_user', 'user_id': 1, 'gallery_user': True, 'hidden': True,
             'footage': {'type': 'virtual', 'status': 'testing', 'meta': {}}}}
    ],
    'put_tours': [
        {'id': 1, 'title': 'put_tours',
         'body': {'title': 'put_tours', 'hidden': True, 'gallery_user': False, 'meta': {}}},
        {'id': 2, 'title': 'put_tours',
         'body': {'title': 'put_tours', 'gallery_user': False, 'hidden': False, 'meta': {}}},
        {'id': 3, 'title': 'put_tours',
         'body': {'title': None, 'gallery_user': True, 'meta.qwe': '123', 'meta.pp': '565', 'password_in_url': True,
                  'screen@flow': 'TOKEN/panorama.png'}},
        {'id': 4, 'title': 'put_tours',
         'body': {'title': 'put_tours', 'gallery_user': True, 'folder_id': 1, 'meta.some_key1': '123',
                  'meta.some_key2': '565', 'password_in_url': True,
                  'screen@dataurl': datauri.DataURI.from_file('/srv/biganto.com/tests/src/panorama.png')}, },
        {'id': 5, 'title': 'put_tours',
         'body': {'title': 'put_tours', 'gallery_user': None, 'folder_id': None, 'meta.some_key1': None,
                  'meta.some_key2': None, 'password_in_url': True}, },
    ],
    'copy_tour': [
        {'id': 1, 'title': 'copy_tour', 'body': {'title': 'copy_tour'}},
        {'id': 2, 'title': 'copy_tour', 'body': {'title': 'copy_tour_footage', 'copy_footage': 1}},
        {'id': 3, 'title': 'copy_tour', 'body': {'title': 'copy_tour', 'folder_id': 1}},
        {'id': 4, 'title': 'copy_tour', 'body': {'title': 'copy_tour', 'user_id': 1}},
    ],
    'get_tours': [
        {'id': 1, 'title': 'get_tours',
         'query_string': {'user_id': 1}},
        {'id': 2, 'title': 'get_tours',
         'query_string': {'user_id': 1, 'folder_id': None, 'types': 'outside', 'fields': 'id,footage.type'}},
        {'id': 3, 'title': 'get_tours',
         'query_string': {'user_id': 1, 'folder_id': None, 'statuses': 'loading', 'fields': 'id,footage.status'}},
    ]
}


USERS = {}
TOURS = {}
FOOTAGES = {}
STATUSES = Footage.STATUSES
# Каким юзерам добавили продукт virtoaster
PLAN_IDS = {1: 20, 2: 10, 3: 10, 4: 10, 5: 10}

def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3, 6 - нормальные, 4 - забаненный и 5 - удалённый
    Создаем по одному туры и съемке каждому юзеру.
    Для каждой съемки съемка создадим каталог для ассетов.
    Добавим для всех юзеров туры и съемки из стека "все типы все статусы"
    Юзеру anna@biganto.com добавим тарифный план Plus, остальным Basic
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.expire_on_commit = False

        users = [
            {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com', },
            {'id': 2, 'name': 'boris', 'email': 'boris@biganto.com', 'team_member': TeamMember(roles=['tours'])},
            {'id': 3, 'name': 'super', 'email': 'super@biganto.com', 'password_hash': User.hash_password('123')},
            {'id': 4, 'name': 'banned', 'email': 'banned@biganto.com', 'banned': True},
            {'id': 5, 'name': 'deleted', 'email': 'deleted@biganto.com',
             'deleted': datetime.datetime.now() - datetime.timedelta(days=1)},
            {'id': 6, 'name': 'oleg', 'email': 'oleg@biganto.com'},
        ]
        for kwargs in users:
            user = User(email_confirmed=True, **kwargs)
            user.auth_tokens.append(
                AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30),
                          ip='0.0.0.0'))
            db.session.add(user)
            db.session.flush()
            if user.id in PLAN_IDS.keys():
                user.set_virtoaster_plan(PLAN_IDS[user.id])
            tour = Tour(id=user.id, user_id=user.id, title='tour',
                        footage=Footage(user_id=user.id, _status='testing', type='real'))
            db.session.add(tour)
            db.session.flush()
            tour.mkdir()
            tour.footage.mkdir()
            unzip_footage_tour('/srv/biganto.com/tests/src/tours/tour-20444.zip', footage=tour.footage, tour=tour)

            db.session.add(Folder(user_id=user.id, title=f'folder_{user.id}'))
            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            USERS[user.id].update({'role_tours': getattr(user.team_member, 'roles', None)})

        db.session.execute("SELECT setval('tours_id_seq', 100)")
        db.session.execute("SELECT setval('footages_id_seq', 100)")

        for user in User.query.all():
            create_tours_footages_various_types(user_id=user.id)
        for tour in Tour.query.all():
            tour.mkdir()
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title', 'hidden')}
            TOURS.update({'in_files': tour.in_files()})

        for footage in Footage.query.all():
            footage.mkdir()
            FOOTAGES[footage.id] = {k: getattr(footage, k) for k in ('id', 'user_id', 'type', '_status')}
            FOOTAGES[footage.id].update({'in_files': footage.in_files()})

        db.session.commit()
        db.session.close()


def teardown_module():
    """
    Удалим все задачи поставленный в очередь
    """
    redis.flushall()


@pytest.mark.access
def test_access_users(api):
    for user_id, user in USERS.items():
        tour_id = user_id
        # Описание: Пытаемся удалить тур
        # Параметры: без токена авторизации. Съемки: status-testing, type-real
        # Ожидаемый результат: 403
        resp = api.delete(f'/tours/{tour_id}')
        assert resp.status_code == 403

        # Описание: Пытаемся изменить тур
        # Параметры: без токена авторизации. Съемки: status-testing, type-real
        # Ожидаемый результат: 403
        resp = api.put(f'/tours/{tour_id}')
        assert resp.status_code == 403

        # Описание: Пытаемся скопировать первый тур к себе
        # Параметры: без токена авторизации
        # Ожидаемый результат: 403
        resp = api.post(f'/tours/{tour_id}/copy')
        assert resp.status_code == 403

        # Описание: Пытаемся изменить тур
        # Параметры: без токена авторизации. Съемки: status-testing, type-real
        # Ожидаемый результат: 403
        resp = api.put(f'/tours/{tour_id}')
        assert resp.status_code == 403


def test_get_tours(api):
    """
    Получить список туров
    GET /tours
    GET /my/tours
    """
    for user_id, user in USERS.items():
        for dataset in datasets['get_tours']:
            if dataset['id'] == 1:
                # Получить туры юзера с указанием user_id=1.
                # Параметры: без токена авторизации.
                # Ожидаемый результат: Без токена авторизации можно получить не сокрытие туры и туры со съемками
                # в статусах 'published', 'testing'
                resp = api.get('/tours', query_string=dataset['query_string'])
                assert resp.status_code == 200
                ids = [elem['id'] for elem in resp.result]
                for id in ids:
                    assert not TOURS[id]['hidden']
                    assert FOOTAGES[id]['_status'] in ('published', 'testing')

                # Получить туры юзера с указанием user_id=1.
                # Параметры: с токеном авторизации
                # Ожидаемый результат: хозяин торов может получить список любых своих туров.
                # Роль tours также может получить список чужих туров в любых статусах
                # Остальные только в статусах 'published', 'testing'
                resp = api.get('/tours', query_string=dataset['query_string'],
                               auth_as=user['email'])
                assert resp.status_code == 200
                ids = [elem['id'] for elem in resp.result]
                for id in ids:
                    if dataset['query_string']['user_id'] == user_id or user['role_tours']:
                        assert FOOTAGES[id]['_status'] in STATUSES
                    else:
                        assert FOOTAGES[id]['_status'] in ('published', 'testing')

            if dataset['id'] in (2, 3):
                # Получить туры юзера с указанием user_id=1.
                # Параметры: указаны параметры ['query_string']['types'] и ['query_string']['statuses']
                # Ожидаемый результат: хозяин торов может получить список любых своих туров.
                # Роль tours также может получить список чужих туров в любых статусах
                # Остальные только в статусах 'published', 'testing'
                resp = api.get('/tours', query_string=dataset['query_string'], auth_as=user['email'])
                assert resp.status_code == 200
                ids = [elem['id'] for elem in resp.result]
                for id in ids:
                    if dataset['query_string']['user_id'] == user_id or user['role_tours']:
                        if dataset['query_string'].get('types'):
                            assert FOOTAGES[id]['type'] == dataset['query_string']['types']
                        if dataset['query_string'].get('statuses'):
                            assert FOOTAGES[id]['_status'] == dataset['query_string']['statuses']
                    else:
                        assert FOOTAGES[id]['_status'] in ('published', 'testing')


def test_get_tour(api):
    """
    Получить свойства одного тура
    GET /tours/<tour_id>

    GET-параметры:
    fields. Какие свойства включить в ответ, список через запятую без пробелов. default=default.
    """
    query_string = {'fields': 'id,title,footage.status'}
    for user_id, user in USERS.items():
        # Пытаемся получить тур
        # Параметры: с токеном авторизации.
        # Ожидаемый результат: Любой авторизированный юзер может получить любой свой тур, тур любого юзера, кроме туров
        # удаленного и забаненного юзера. Так же нельзя получить тур с забаненой съемкой
        for tour_id in range(101, 191):
            if user_id != 2:
                resp = api.get(f'/tours/{tour_id}', query_string=query_string, auth_as=user['email'])
                if (FOOTAGES[tour_id]['_status'] == 'banned'
                    and TOURS[tour_id]['user_id'] != user_id) \
                        or TOURS[tour_id]['user_id'] == 4 \
                        or (TOURS[tour_id]['user_id'] == 5 and not user['deleted']):
                    assert resp.status_code == 403
                else:
                    assert resp.status_code == 200
            else:
                # Роль tours может получить любой тур
                resp = api.get(f'/tours/{tour_id}', query_string=query_string, auth_as=user['email'])
                assert resp.status_code == 200

    # Пытаемся получить тур
    # Параметры: без токена авторизации.
    # Ожидаемый результат: можно получить любой тур, кроме туров
    # удаленного и забаненного юзера. Так же нельзя получить тур с забаненой съемкой
    for tour_id in range(101, 191):
        resp = api.get(f'/tours/{tour_id}', query_string=query_string)
        if FOOTAGES[tour_id]['_status'] == 'banned' or TOURS[tour_id]['user_id'] == 4 or TOURS[tour_id]['user_id'] == 5:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200


def test_copy_tour(api):
    """
    Копируем тур
    POST /tours/<tour_id>/copy
    тело
    {
    "user_id": int,   // Какому пользователю отдать копию тура.
    "folder_id": int, // В какую папку копировать. null — в корень; если свойство не указано,
                      // то тур скопируется в ту же папку, где и был.
    "title": str      // Название нового тура. Если свойство не указано, то название будет тем же, что и у исходного.
    "copy_footage": int  // значения 1 - копирование тура со съемкой, 0 - без копирования съемки, default - 0
    }
    todo: скопировать тур удаленному юзеру не может никто: ни роль tours, ни он сам
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        folder_id = tour_id
        for dataset in datasets['copy_tour']:

            if dataset['id'] in (1, 2, 3):
                if dataset['body'].get('folder_id', None):
                    dataset['body']['folder_id'] = folder_id

                # Описание: Пытаемся скопировать тур
                # Параметры: с токеном авторизации. Копируем себе - user_id не указан. Тур с id=1
                # Ожидаемый результат: Любой юзер кроме забаненного и удаленного может скопировать себе тур
                resp = api.post(f'/tours/{tour_id}/copy', body=dataset['body'], auth_as=user['email'])
                if user['banned'] or user['deleted'] or user_id == 6:
                    assert resp.status_code in (400, 403)
                else:
                    assert resp.status_code == 200
                    assert 'bgjobs' in resp.object

            if dataset['id'] in (4,):
                # Описание: Пытаемся скопировать тур
                # Параметры: с токеном авторизации. Копируем другому - user_id указан.
                # Ожидаемый результат: скопировать тур может только владелец и только себе.
                # Роль 'tours' - любому, но не удалённому.
                # Забаненый и удаленный скопировать тур не могут
                for body_user_id in range(1, 5):
                    dataset['body']['user_id'] = body_user_id
                    resp = api.post(f'/tours/{tour_id}/copy',
                                    body=dataset['body'], auth_as=user['email'])

                    if user['role_tours'] or dataset['body']['user_id'] == user_id and user_id != 4and user_id != 6:
                        assert resp.status_code == 200
                        assert 'bgjobs' in resp.object
                    elif user['banned']:
                        assert resp.status_code == 403
                        assert resp.has_error('User banned.')
                    elif user_id == 6:
                        assert resp.status_code == 403
                    else:
                        assert resp.status_code == 403
                        assert resp.has_error('You can not copy tours to other accounts.')

                # Описание: Пытаемся скопировать тур удаленному юзеру
                # Ожидаемый результат: скопировать тур удаленному юзеру НЕЛЬЗЯ
                dataset['body']['user_id'] = 5
                resp = api.post(f'/tours/{tour_id}/copy', body=dataset['body'], auth_as=user['email'])
                assert resp.status_code == 403
                if user['role_tours'] or user['deleted']:
                    resp.has_error('You can not copy tours to deleted users.')
                elif user['banned']:
                    assert resp.has_error('User banned.')
                elif user_id == 6:
                    assert resp.has_error('You can not copy this tour, tours limit exceeded.')
                else:
                    assert resp.has_error('You can not copy tours to other accounts.')


def test_post_tours(api):
    """
    Создание тура
    POST /tours
    POST /my/tours

    тело запроса
    "user_id": int,
    "folder_id": int=null,
    "title": str=null,
    "meta": object={},
    "hidden": bool=false,
    "gallery_user": bool=false,
    "assets": "upload-slot@upload1.biganto.com/SLUT",  // Можно залить ассеты тура из Upload Slot'а
    "footage_id": int | null
    // Если fotage_id не указан, то съёмку можно сразу создать:
    "footage": {
        "type": str,
        "status": str,
        "meta": object={}
    }

    """
    for user_id, user in USERS.items():
        for dataset in datasets['post_tour']:
            if dataset['id'] in (1, 2, 3):
                for url in ['/tours', '/my/tours']:

                    # Описание: Пытаемся добавить тур
                    # Ожидаемый результат: Любой юзер кроме забаненного и удаленного может добавить тур
                    resp = api.post(url, body=dataset['body'], auth_as=user['email'])
                    if user['banned'] or user['deleted']:
                        assert resp.status_code == 403
                    else:
                        assert resp.status_code == 200

                        # Параметры: Используем существующую съемку - указан footage_id
                        # Ожидаемый результат: будет создан тур со съемкой, id который равен footage_id
                        if dataset['body'].get('footage_id', None):
                            # Проверяем, что id нового тура нет в TOURS, а id съемки одинаковый
                            assert resp.result['id'] not in TOURS.keys()
                            assert resp.result['footage_id'] == dataset['body']['footage_id']
                        else:

                            # Параметры: Создаем новую съемку - в теле указан footage = {..}
                            # Ожидаемый результат: будет создан тур с новой съемкой
                            # Проверяем, что id нового тура нет в FOOTAGES - тур новый
                            assert resp.result['id'] not in TOURS.keys()
                            assert resp.result['footage_id'] not in FOOTAGES.keys()

            # Описание: Пытаемся добавить тур.
            # Параметры: Создаем тур другому юзеру - в теле указан 'user_id'
            # Параметры: url = /tours
            # Ожидаемый результат: Только роль tours может создавать туры другим юзерам, остальные создают только себе
            if dataset['id'] in (4, 5):
                url = '/tours'
                resp = api.post(url, body=dataset['body'], auth_as=user['email'])
                if user['role_tours'] or dataset['body']['user_id'] == user_id:
                    assert resp.status_code == 200
                    # Проверяем, если что тур создался другому юзеру
                    assert dataset['body']['user_id'] == resp.result['user_id']

                    # Параметры: Используем существующую съемку - указан footage_id
                    # Ожидаемый результат: будет создан тур со съемкой, id который равен footage_id
                    if dataset['body'].get('footage_id', None):

                        # Проверяем, что id нового тура нет в TOURS, а id съемки одинаковый
                        assert resp.result['id'] not in TOURS.keys()
                        assert resp.result['footage_id'] == dataset['body']['footage_id']
                    else:
                        # Параметры: Создаем новую съемку - в теле указан footage = {..}
                        # Ожидаемый результат: будет создан тур с новой съемкой
                        # Проверяем, что id нового тура нет в TOURS, а id съемки в FOOTAGES
                        assert resp.result['id'] not in TOURS.keys()
                        assert resp.result['footage_id'] not in FOOTAGES.keys()
                elif user['banned']:
                    assert resp.status_code == 403
                    assert resp.has_error('User banned.')
                else:
                    assert resp.status_code == 403
                    assert resp.has_error('You can not create tours for other users.')

                # Описание: Пытаемся добавить тур.
                # Параметры: Создаем тур другому юзеру - в теле указан 'user_id'
                # Параметры: url = /my/tours
                # Ожидаемый результат:
                url = '/my/tours'
                resp = api.post(url, body=dataset['body'], auth_as=user['email'])
                # Пользователь с ролью 'tours' , владелец или url = my/tours
                if user['banned'] or user['deleted']:
                    assert resp.status_code == 403
                else:
                    assert resp.status_code == 200
                    if user_id == 1:
                        assert dataset['body']['user_id'] == resp.result['user_id']
                    else:
                        assert dataset['body']['user_id'] != resp.result['user_id']


def test_post_tour_seen(api):
    """
    Пометить тур как просмотренный
    POST /tours/<tour_id>/seen
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        # Описание: Пытаемся пометить тур как просмотренный
        # Параметры: без токена авторизации. Съемки: status-testing, type-real
        # Ожидаемый результат: Без автовризации можно пометить тур как просмотренный, только не тур забаненного и удалекнного юзера
        resp = api.post(f'/tours/{tour_id}/seen')
        if user['banned'] or user['deleted'] or user_id == 6:
            assert resp.status_code == 403
            if user['banned']:
                assert resp.has_error('Owner of this tour has been banned.')
            if user['deleted']:
                assert resp.has_error('Owner of this tour has been deleted.')
            if user_id == 6:
                assert resp.has_error('You can not view this tour.')
        else:
            assert resp.status_code == 204

        # Описание: Пытаемся пометить тур как просмотренный
        # Параметры: без токена авторизации. Съемки: status-testing, type-real
        # Ожидаемый результат: Любой юзер кроме забаненного и удаленного может пометить тур как просмотренный
        resp = api.post(f'/tours/{tour_id}/seen', auth_as=user['email'])
        if user['banned']:
            assert resp.status_code == 403
            assert resp.has_error('Owner of this tour has been banned.')
        else:
            assert resp.status_code == 204


def test_get_tour_assets(api):
    """
    Получить ассеты тура и съёмки
    /tours/<tour_id>/assets
    """
    for user_id, user in USERS.items():

        tour_id = user_id
        # Описание: Пытаемся получить ассеты тура
        # Параметры: без токена авторизации. Съемки: status-testing, type-real
        # Ожидаемый результат: Без авторизации можно получить ассеты любого тура, кроме тура забаненного,удаленного
        # и юзеру без подписки 'virtoaster'
        resp = api.get(f'/tours/{tour_id}/assets')
        if TOURS[tour_id]['user_id'] in (4, 5, 6):
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200
            assert resp.result



@pytest.mark.bad_requests
def test_bad_requests_delete_meta_selector(api):
    """
        Плохие запросы
    """

    # Перед тестами сделаем снимок с tour.meta
    query_string = {'fields': 'meta'}
    check_resp = api.get(f'/tours/1', auth_as='anna@biganto.com', query_string=query_string)
    meta_before = check_resp.result

    # Параметры: не указан селектор
    resp = api.delete(f'/tours/1/meta', auth_as='anna@biganto.com')
    assert resp.status_code == 404
    assert resp.has_error('The requested URL was not found on the server')

    # Параметры: nonexistent - не существует
    resp = api.delete(f'/tours/1/meta.nonexistent', auth_as='anna@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Malformed nonexistent value. ')

    # Параметры: start.q - существует q1 - не существует
    resp = api.delete(f'/tours/1/meta.start.q.q1', auth_as='anna@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Malformed q1 value. ')

    # Параметры: start.q. и start.skybox- существуют.
    resp = api.delete(f'/tours/1/meta.start.q.skybox', auth_as='anna@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Malformed skybox value. ')

    # Параметры: skyboxes.1.title - существует. Попытка обратиться к ключу, минуя промежуточный
    resp = api.delete(f'/tours/1/meta.skyboxes.title', auth_as='anna@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Malformed title value. ')

    # Сравниванием tour.meta до и после тестов. После всех тестов tour.meta не должна быть измененной
    check_resp = api.get(f'/tours/1', auth_as='anna@biganto.com', query_string=query_string)
    meta_after = check_resp.result
    assert meta_before == meta_after

def test_delete_meta_selector(api):
    """
    DELETE /tours/<tour_id>/meta.<selector>
    Проверяем удаление ключей в  tour.meta по селектору
    Для проверки правильности удаления используется дополнительный API метод GET /tours/<tour_id>
    """
    for user_id, user in USERS.items():
        tour_id = user_id

        # Описание: Пытаемся удалить свойства в tour.meta по селектору
        # Параметры: С токеном авторизации.
        # Ожидаемый результат: 204
        # Любой юзер кроме забаненного может удалить свойства в tour.meta по селектору
        # Доказательств: при помощи GET запроса запрашиваем 'selector' до запроса на удаление и после

        # SET 1
        # Первый уровень вложенности
        selector = 'meta.start'
        query_string = {'fields': f'{selector}'}
        check_resp = api.get(f'/tours/{tour_id}', auth_as=user['email'], query_string=query_string)
        # Проверим, что селектор существовал
        if not user['banned']:
            assert check_resp.status_code == 200
            assert selector in check_resp.result

        resp = api.delete(f'/tours/{tour_id}/{selector}',  auth_as=user['email'])
        check_resp = api.get(f'/tours/{tour_id}', auth_as=user['email'], query_string=query_string)
        # Проверяем, что селектор удален и что повторный GET запрос к туру не вернет этот селектор
        if not user['banned']:
            assert resp.status_code == 204
            assert check_resp.has_warning(f'Unknown field {selector}')
            assert selector not in check_resp.result
        else:
            assert resp.status_code == 403

        # SET 2
        # Проверим, что удаляется двойная вложенность селекторов и не удаляется промежуточные секторы
        selector = 'meta.skyboxes.2'
        query_string = {'fields': f'{selector}'}
        check_resp = api.get(f'/tours/{tour_id}', auth_as=user['email'], query_string=query_string)
        if not user['banned']:
            assert check_resp.status_code == 200
            assert selector in check_resp.result
        else:
            assert check_resp.status_code == 403

        resp = api.delete(f'/tours/{tour_id}/{selector}', auth_as=user['email'])
        if not user['banned']:
            assert resp.status_code == 204
        else:
            assert resp.status_code == 403

        # Проверяем, что повторный GET запрос к туру не вернет этот селектор
        check_resp = api.get(f'/tours/{tour_id}', auth_as=user['email'], query_string=query_string)
        if not user['banned']:
            assert check_resp.status_code == 200
            assert check_resp.has_warning(f'Unknown field {selector}')
            assert selector not in check_resp.result

        # Проверяем GET запрос к промежуточному селектору
        selector = 'meta.skyboxes'
        query_string = {'fields': f'{selector}'}
        check_resp = api.get(f'/tours/{tour_id}', auth_as=user['email'], query_string=query_string)
        if not user['banned']:
            assert check_resp.status_code == 200
            assert selector in check_resp.result

        # SET 3
        # Попытка удалить тройную вложенность селекторов. Селектор должен удалится, промежуточные - нет
        selector = 'meta.skyboxes.1.title'
        query_string = {'fields': f'{selector}'}
        check_resp = api.get(f'/tours/{tour_id}', auth_as=user['email'], query_string=query_string)
        # Проверяем, что селектор существовал
        if not user['banned']:
            assert check_resp.status_code == 200
            assert selector in check_resp.result

        resp = api.delete(f'/tours/{tour_id}/{selector}', auth_as=user['email'])
        if not user['banned']:
            assert resp.status_code == 204
        else:
            assert resp.status_code == 403

        # Проверяем, что повторный GET запрос к туру не вернет этот селектор
        check_resp = api.get(f'/tours/{tour_id}', auth_as=user['email'], query_string=query_string)
        if not user['banned']:
            assert check_resp.status_code == 200
            assert check_resp.has_warning(f'Unknown field {selector}')
            assert selector not in check_resp.result

        # Проверяем GET запрос к промежуточным селекторам
        selectors = ['meta.skyboxes.1','meta.skyboxes',]
        for selector in selectors:
            query_string = {'fields': f'{selector}'}
            check_resp = api.get(f'/tours/{tour_id}', auth_as=user['email'], query_string=query_string)
            if not user['banned']:
                assert check_resp.status_code == 200
                assert selector in check_resp.result

def test_put_tour(api):
    """
    Изменить свойства тура
    PUT /tours/<tour_id>

    Тело запроса:
    {
    "title": str,
    "hidden": bool,
    "gallery_user": bool,
    "folder_id": int|null             // Чтобы поместить тур в корень, поместите сюда null
    "screen@flow": "TOKEN/filename",  // Можно залить превьюшку через flow
    "screen@dataurl": str,            // А можно отдать картинку в виде Data URL
    "assets": "upload-slot@upload1.biganto.com/SLUT",  // Можно залить ассеты тура из Upload Slot'а
    "meta",                           // Можно сразу перезаписать всю мету...
    "meta.selector1": any,            // ...но лучше через селектор изменить нужное свойство меты
    "meta.selector2": any,            // ...и не одно
    }
    """

    for user_id, user in USERS.items():
        tour_id = user_id
        folder_id = tour_id
        for dataset in datasets['put_tours']:


            # Описание: Пытаемся изменить тур
            # Параметры: с токеном авторизации. Съемки: status-testing, type-real
            # Параметры: с токеном авторизации. Съемки: status-testing, type-real
            # Ожидаемый результат: Любой юзер кроме забаненного и удаленного может изменить свой тур
            if dataset['body'].get('screen@flow', None):
                set_flow({'TOKEN': ['src/panorama.png']})

            if dataset['body'].get('folder_id', None):
                dataset['body']['folder_id'] = folder_id

            resp = api.put(f'/tours/{tour_id}', body=dataset['body'], auth_as=user['email'])
            if not user['banned']:
                assert resp.status_code == 200
            else:
                assert resp.status_code == 403

            # Описание: Пытаемся изменить тур
            # Параметры: Роль tours. Тур в статусе - banned, user_id тура - 4
            # Ожидаемый результат: Роль tours может изменить любой тур
            if dataset['id'] == 1:
                resp = api.put(f'/tours/172',
                               body=dataset['body'], auth_as='boris@biganto.com')
                assert resp.status_code == 200


@pytest.mark.bad_requests
def test_exceptions(api):
    """
    Плохие запросы
    """
    # Описание: Пытаемся удалить тур
    # Параметры: Нет такого тура
    resp = api.delete(f'/tours/300', auth_as='anna@biganto.com')
    assert resp.status_code == 404
    assert resp.has_error('Tour not found.')

    # Описание: Пытаемся изменить тур
    # Параметры: Чужая папка
    body = {'title': 'put_tours', 'gallery_user': True, 'hidden': True, 'password': '123', 'password_in_url': True,
            'folder_id': 100}
    resp = api.put(f'/tours/1', auth_as='anna@biganto.com', body=body)
    assert resp.status_code == 404
    assert resp.has_error('Target folder not found.')

    # Описание: Пытаемся изменить тур
    # Параметры: неизвестное свойство
    body = {'title': 'put_tours', 'gallery_user': True, 'hidden': False, 'password': '123', 'password_in_url': "True",
            'folder_id': 3, 'some_val': 'some_key'}
    resp = api.put(f'/tours/3', auth_as='super@biganto.com', body=body)
    assert resp.status_code == 200
    assert resp.has_warning('Property some_val not found.')

    # Описание: Пытаемся изменить тур
    # Параметры: Нет такого тура
    body = {'title': 'put_tours', 'gallery_user': True, 'hidden': True, 'password': '123', 'password_in_url': "True",
            'folder_id': 1, 'meta': 'some_key'}
    resp = api.put(f'/tours/1', auth_as='anna@biganto.com', body=body)
    assert resp.status_code == 400
    assert resp.has_error('Bad data type for property meta')

    # Описание: Пытаемся изменить тур
    # Параметры: Нет TOKEN/panorama.png
    body = {'title': 'put_tours', 'gallery_user': True, 'hidden': True, 'password': '123', 'password_in_url': "True",
            'folder_id': 1, 'screen@flow': 'TOKEN/nonexisting.png'}
    shutil.rmtree('/srv/biganto.com/var/flow-upload/TOKEN', ignore_errors=True)
    resp = api.put(f'/tours/1', auth_as='anna@biganto.com', body=body)
    assert resp.status_code == 400
    assert resp.has_error('Source file TOKEN/nonexisting.png not found for screen@flow.')

    # Описание: Пытаемся пометить тур как просмотренный
    # Параметры: нет такого тура
    resp = api.post(f'/tours/300/seen', auth_as='anna@biganto.com', body=body)
    assert resp.status_code == 404
    assert resp.has_error('Tour not found.')

    # Описание: Пытаемся добавить тур
    # Параметры: отсутствует обязательный параметр: footage_id или footage
    body = {'title': 'post_tour'}
    resp = api.post(f'/tours', auth_as='anna@biganto.com', body=body)
    assert resp.status_code == 400
    assert resp.has_error('You should specify either footage_id or footage in input data.')

    # Описание: Пытаемся добавить тур
    # Параметры: присутствуют оба параметра: footage_id и footage
    body = {'title': 'post_tour', 'footage': {}, 'footage_id': 1}
    resp = api.post(f'/tours', auth_as='anna@biganto.com', body=body)
    assert resp.status_code == 400
    assert resp.has_error('You can not specify both footage_id and footage in input data.')

    # Описание: Пытаемся добавить тур
    # Параметры: съемки с таким footage_id не существует
    # Комментарий: todo: Отсутствует проверка на существование съемки с таким id
    body = {'title': 'post_tour', 'footage_id': 1}
    resp = api.post(f'/tours', auth_as='anna@biganto.com', body=body)

    # Описание: Пытаемся добавить тур
    # Параметры: нет юзера с таким id
    body = {'title': 'post_tour', 'footage': {}, 'user_id': 100}
    resp = api.post(f'/tours', auth_as='anna@biganto.com', body=body)
    assert resp.status_code == 400
    assert resp.has_error('User id="100" not found.')

    # Описание: Пытаемся скопировать тур
    # Параметры: у юзера с тарифным планом Basic превышен лимит 'storage': 20 в PLANS
    body = {'title': 'copy_tour'}
    resp = api.post(f'/tours/1/copy', auth_as='super@biganto.com', body=body)
    assert resp.status_code == 403

    # Описание: Пытаемся скопировать тур
    # Параметры: неверный формат copy_footage
    body = {'title': 'copy_tour', 'copy_footage': 'ads'}
    resp = api.post(f'/tours/1/copy', auth_as='anna@biganto.com', body=body)
    assert resp.status_code == 400
    assert resp.has_error('Bad data type for property copy_footage')
    # Параметры: Нет такой папки
    body = {'title': 'copy_tour', 'folder_id': 200}
    resp = api.post(f'/tours/1/copy', auth_as='anna@biganto.com', body=body)
    assert resp.status_code == 400
    assert resp.has_error('Target folder not found.')

    # Описание: Пытаемся скопировать тур
    # Параметры: Юзер не может копировать туры другим
    body = {'title': 'copy_tour', 'user_id': 200}
    resp = api.post(f'/tours/1/copy', auth_as='anna@biganto.com', body=body)
    assert resp.status_code == 403
    assert resp.has_error('You can not copy tours to other accounts.')

    # Описание: Пытаемся скопировать тур
    # Параметры: Юзер может копировать туры другим, но юзера с таким id нет
    body = {'title': 'copy_tour', 'user_id': 200}
    resp = api.post(f'/tours/1/copy', auth_as='boris@biganto.com', body=body)
    assert resp.status_code == 400
    assert resp.has_error('Target user 200 not found.')

    # Описание: Пытаемся получить список туров
    # Параметры: отсутствует обязательный параметр: user_id
    query_string = {}
    resp = api.get(f'/tours', auth_as='anna@biganto.com', query_string=query_string)
    assert resp.status_code == 400
    assert resp.has_error('Please specify user_id.')

    # Описание: Пытаемся получить список туров
    # Параметры: юзер не найден
    query_string = {'user_id': 200}
    resp = api.get(f'/tours', auth_as='anna@biganto.com', query_string=query_string)
    assert resp.status_code == 404
    assert resp.has_error('User not found.')

    # Описание: Пытаемся получить список туров
    # Параметры: Папки с таки id не существует
    query_string = {'user_id': 1, 'folder_id': 100, 'statuses': 'loading', 'fields': 'id,footage.status'}
    resp = api.get(f'/tours', auth_as='anna@biganto.com', query_string=query_string)
    assert resp.status_code == 404
    assert resp.has_error('Folder not found.')

    # Описание: Пытаемся получить список туров
    # Параметры: Папки с таки id существует, но принадлежит другому юзеру
    query_string = {'user_id': 1, 'folder_id': 2, 'statuses': 'loading', 'fields': 'id,footage.status'}
    resp = api.get(f'/tours', auth_as='anna@biganto.com', query_string=query_string)
    assert resp.status_code == 404
    assert resp.has_error('Folder not found.')

    # Описание: Пытаемся получить список туров
    # Параметры: несуществующий статус съемки
    query_string = {'user_id': 1, 'folder_id': 1, 'statuses': 'loading1', 'types': 'real', 'fields': 'id,footage.status'}
    resp = api.get(f'/tours', auth_as='anna@biganto.com', query_string=query_string)
    assert resp.status_code == 400
    assert resp.has_error('Wrong statuses parameters: loading1.')

    # Описание: Пытаемся получить список туров
    # Параметры: несуществующий статус съемки
    query_string = {'user_id': 1, 'folder_id': 1, 'statuses': 'loading', 'types': 'real_', 'fields': 'id,footage.status'}
    resp = api.get(f'/tours', auth_as='anna@biganto.com', query_string=query_string)
    assert resp.status_code == 400
    assert resp.has_error('Wrong types parameters: real_.')

    # Описание: Пытаемся получить список туров
    # Параметры: случайный ключ
    query_string = {'user_id': 1, 'folder_id': 1, 'some_key': 'some_val', 'types': 'real', 'fields': 'id,footage.status'}
    resp = api.get(f'/tours', auth_as='anna@biganto.com', query_string=query_string)
    assert resp.status_code == 200

    # Описание: Пытаемся получить туров
    # Параметры: случайный ключ
    query_string = {'fields': 'id,footage.status'}
    resp = api.get(f'/tours/100', auth_as='anna@biganto.com', query_string=query_string)
    assert resp.status_code == 404
    assert resp.has_error('Tour not found.')


def test_delete_tour(api):
    """
    DELETE /tours/<tour_id>
    Удаляет тур и его ассеты.
    
    """
    for user_id, user in USERS.items():
        tour_id = user_id

        # Описание: Пытаемся удалить тур
        # Параметры: с токеном авторизации. Съемки: status-testing, type-real
        # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может удалить свою съемку.
        # Комментарий: метод удаляет съёмку, если у неё больше не осталось туров.
        resp = api.delete(f'/tours/{tour_id}', auth_as=user['email'])
        if user['banned']:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 204

    # Описание: Пытаемся удалить тур
    # Параметры: Роль tours. Тур в статусе - banned, user_id тура - 4
    # Ожидаемый результат: Роль tours может удалить о любой тур
    resp = api.delete(f'/tours/172', auth_as='boris@biganto.com')
    assert resp.status_code == 204
