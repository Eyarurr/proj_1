import datetime

from visual import create_app
from visual.core import db
from visual.models import User, Folder, Tour, Footage, TeamMember, AuthToken

datasets = {'folder_post': {'id': 1, 'title': 'add_folder',
                            'description': 'Создаем папку себе, другу',
                            'body': {
                                "title": "Название папки"},
                            },
            'folder_put': {'id': 2, 'title': 'put_folder',
                           'description': 'Попытка изменить folder.',
                           'body': {
                               "title": 'Новое название папки',
                           },
                           },
            'get_folders': {'id': 3, 'title': 'get_folders', 'url': 'GET /users/<user_id>/folders GET /my/folders',
                            'description': 'Попытка получить список папок юзера',
                            'query_string': {'sort': 'title'}
                            },
            'get_folder': {'id': 4, 'title': 'get_folder',
                           'url': 'GET /users/<user_id>/folders/<folder_id, /my/folders/<folder_id>',
                           'description': ' Попытка получить папку юзера',
                           },
            'del_folder': {'id': 5, 'title': 'del_folder',
                           'description': 'Попытка удалить папку',
                           'query_string': {'delete_tours': True}
                           },

            }

USERS = {}
FOLDERS = {}


def setup_module():
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()

        users = [
            User(id=1, name='anna', email='anna@biganto.com', email_confirmed=True, ),
            User(id=2, name='boris', email='boris@biganto.com', email_confirmed=True,
                 team_member=TeamMember(roles=['tours'])),
            User(id=3, name='super', email='super@biganto.com', email_confirmed=True, ),
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
            folder = Folder(user_id=user.id)
            db.session.add(folder)
            db.session.flush()
            tour = Tour(user_id=user.id, title=f'Starting tour us{user.id}', meta={"key": "Некая мета"},
                        footage=Footage(user_id=user.id, _status='testing', type='real'), folder_id=folder.id
                        )
            db.session.add(tour)
            db.session.flush()

            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            FOLDERS[folder.id] = {k: getattr(folder, k) for k in ('id', 'user_id', 'title')}

        db.session.execute("SELECT setval('tours_id_seq', 100)")
        db.session.execute("SELECT setval('footages_id_seq', 100)")
        db.session.execute("SELECT setval('folders_id_seq', 100)")
        db.session.commit()


def test_post_folder(api):
    """
    Создать папку
    POST /users/<user_id>/folders
    POST /my/folders
    todo для POST folders.py  POST /users/<user_id>/folders нет проверки, если request.json is None
    """
    dataset = datasets['folder_post']
    for user_id, user in USERS.items():
        for url, title in [
            (f'/users/{user["id"]}/folders', f'{user["email"]} добавил папку юзеру {user["id"]}'),
            ('/my/folders', f'/my/folders от юзера {user["email"]}')
        ]:
            dataset['body']['title'] = title

            # Создаем папку без авторизации
            # Ожидаемый результат: 403
            resp = api.post(url, body=dataset['body'])
            assert resp.status_code == 403

            # Создаем папку с авторизацией
            # Ожидаемый результат: создать папку может только владелец. По адресу /my/folders добавляется
            # папка авторизированному юзеру. Забаненный не может добавлять
            resp = api.post(url, body=dataset['body'], auth_as=user["email"])
            if user["email"] != 'banned@biganto.com':
                assert resp.status_code == 200
                FOLDERS[resp.result['id']] = resp.result
            else:
                assert resp.status_code == 403


def test_put_folder(api):
    """
    Сохранить папку
    PUT /users/<user_id>/folders/<folder_id>
    PUT /my/folders/<folder_id>
    """
    dataset = datasets['folder_put']
    for user_id, user in USERS.items():
        for folder_id in range(1, len(FOLDERS) + 1):
            for url, title in [
                (f'/users/{user["id"]}/folders/{folder_id}', f'{user["email"]} изменил папку юзеру {user["email"]}'),
                (f'/my/folders/{folder_id}', f'/my/folders/{folder_id} юзер {user["id"]}')
            ]:
                dataset['body']['title'] = title
                # Создаем папку с авторизацией
                # Ожидаемый результат: изменить папку может только владелец. По адресу /my/folders добавляется
                # папка авторизированному юзеру. Забаненный не может добавлять
                resp = api.put(url, body=dataset['body'], auth_as=user["email"])
                if folder_id == user['id'] and user['email'] != 'banned@biganto.com':
                    assert resp.status_code == 200
                else:
                    assert resp.status_code == 403 or resp.status_code == 404


def test_get_folders(api):
    """
    Получить папки юзера
    GET /users/<user_id>/folders
    GET /my/folders
    :param api:
    :return: 
    """
    dataset = datasets['get_folders']
    for user_id, user in USERS.items():
        for url in [f'/users/{user["id"]}/folders', f'/my/folders']:
            # Получаем список папок без авторизации
            # Ожидаемый результат: 403
            resp = api.get(url)
            assert resp.status_code == 403
            # Получаем список папок
            # Ожидаемый результат: Список папок может получить владелец. Забаненный не может
            resp = api.get(url, auth_as=user["email"])
            if not user['banned']:
                assert resp.status_code == 200
            else:
                assert resp.status_code == 403 or resp.status_code == 404

            # Получаем список папок. Сортируем их. {'sort': 'title'}
            # Ожидаемый результат: Список папок может получить владелец. Забаненный не может
            resp = api.get(url, query_string=dataset['query_string'], auth_as=user['email'])
            if not user['banned']:
                assert resp.status_code == 200
            else:
                assert resp.status_code == 403 or resp.status_code == 404


def test_get_folder(api):
    """
    Получить папку
    GET /users/<user_id>/folders/<folder_id>
    GET /my/folders/<folder_id>
    :return:
    """
    for user_id, user in USERS.items():
        folder_id = user['id']
        for url in [f'/users/{user["id"]}/folders/{folder_id}', f'/my/folders/{folder_id}']:
            # Получаем список папок без авторизации
            # Ожидаемый результат: 403
            resp = api.get(url)
            assert resp.status_code == 403
            # Получаем список папок
            # Ожидаемый результат: Список папок может получить владелец. Забаненный не может
            resp = api.get(url, auth_as=user['email'])
            if not user['banned']:
                assert resp.status_code == 200
            else:
                assert resp.status_code == 403 or resp.status_code == 40


def test_del_folder(api):
    """
    Удаляем папку
    DELETE /users/<user_id>/folders/<folder_id>
    DELETE /my/folders/<folder_id>
    :param api:
    :return:
    """
    dataset = datasets['del_folder']
    for user_id, user in USERS.items():
        tour_id = user['id']
        folder_id = user['id']
        url = f'/users/{user["id"]}/folders/{folder_id}'
        # Пробуем удалить папки пользователей без авторизации
        # ожидаемый результат: 403
        resp = api.delete(url)
        assert resp.status_code == 403
        # Пробуем удалить свои папки с авторизацией. Тело запроса {'delete_tours': True}
        # ожидаемый результат: удалить сои папки может любой юзер, кроме забаненного.
        # Туры будут удалены
        resp = api.delete(url, query_string=dataset['query_string'], auth_as=user['email'])

        # Проверяем: загружаем свойства тура (он должен быть удалён)
        tour_query = api.get(f'/tours/{tour_id}')
        if not user['banned']:
            assert tour_query.status_code == 404
            assert resp.status_code == 204
        else:
            assert resp.status_code == 403 or resp.status_code == 404

        if user['id'] == 1:
            # Пробуем удалить свои папки с авторизацией. Тело запроса пустое
            # ожидаемый результат: удалить сои папки может любой юзер, кроме забаненного.
            # Туры переехали в корень
            for url in [f'/users/{user["id"]}/folders/101', f'/my/folders/102']:
                resp = api.delete(url, auth_as=user["email"])
                assert resp.status_code == 204
