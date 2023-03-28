import datetime

import pytest

from visual import create_app
from visual.core import db
from visual.models import User, Tour, TeamMember, Footage, AuthToken
from .common import set_flow

USERS = {}
TOKENS = {}
ALLTOKENS = []
TOURS = {}
FOOTAGES = {}

datasets = {
    'put_users': {
        '1': {'id': 1, 'title': 'put_tour', 'description': '', 'query_string': {'fields': 'id,email,timezone,settings'},
              'body': {'name': str, 'email': str, 'timezone': 'Etc/GMT-3', 'email_notifications': False,
                       'settings': {'filincam': {'autoprocess': True}}
                       }
              },
        '2': {'id': 1, 'title': 'put_tour', 'description': '', 'query_string': {'fields': 'id,email,timezone,settings'},
              'body': {'name': str, 'timezone': 'Etc/GMT-4',
                       },
              }
    },
}


def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3 - нормальные, 4 - забаненный и 5 - удалённый
    Создаем по одному туры и съемке каждому юзеру.
    Добавляем роли
    anna@biganto.com- admin.access
    boris@biganto.com - tours
    super@biganto.com - super
    users@biganto.com - users
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.expire_on_commit = False

        users = [
                {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com', 'team_member': TeamMember(roles=['admin.access'])},
                {'id': 2, 'name': 'boris', 'email': 'boris@biganto.com', 'team_member': TeamMember(roles=['tours'])},
                {'id': 3, 'name': 'super', 'email': 'super@biganto.com', 'team_member': TeamMember(roles=['super'])},
                {'id': 4, 'name': 'users', 'email': 'users@biganto.com', 'team_member': TeamMember(roles=['users'])},
                {'id': 5, 'name': 'banned', 'email': 'banned@biganto.com', 'banned': True},
                {'id': 6, 'name': 'deleted', 'email': 'deleted@biganto.com', 'deleted': datetime.datetime.now() - datetime.timedelta(days=1)},
                {'id': 7, 'name': 'anna2', 'email': 'anna2@biganto.com', },
            ]
        for kwargs in users:
            user = User(email_confirmed=True, password_hash=User.hash_password('123'), **kwargs, )
            db.session.add(user)
            db.session.flush()
            token = AuthToken(user_id=user.id, signature=user.email,
                              expires=datetime.datetime.now() + datetime.timedelta(days=30), ip='0.0.0.0')
            db.session.add(token)
            tour = Tour(id=user.id, user_id=user.id, title='tour',
                        footage=Footage(user_id=user.id, _status='testing', type='real'))
            db.session.add(tour)
            db.session.flush()
            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted', 'settings', 'admin_comment', '_timezone')}
            USERS[user.id].update({'role_tours': getattr(user.team_member, 'roles', None)})
            TOKENS[user.id] = {k: getattr(token, k) for k in ('user_id', 'ip', 'expires', 'signature', 'id')}
            ALLTOKENS.append(token.signature)
        db.session.commit()
        db.session.close()


def test_post_user_login(api):
    """
    Авторизация
    POST /users/login

    Тело запроса:
    {
    'email': str,
    'password': str,
    'expires': str, // дата и время потухания токена авторизации
    'title': str  // название токена.
    }
    todo: этот кейс протестировать невозможно из-за ошибки получение ip при создании токена. Для тестирования сделал костыль в api3/users.py
    sqlalchemy.exc.IntegrityError: (psycopg2.errors.NotNullViolation) null value in column "ip" violates not-null constraint
    """
    for user_id, user in USERS.items():
        body = {'email': user['email'], 'password': '123'}

        # Описание: пытаемся создать токен авторизации
        # Параметры: без токена авторизации
        # Ожидаемый результат: Создать токен авторизации можно для любого юзера, кроме удаленного и забаненного юзера,
        # если указаны правильные логин и пароль
        resp = api.post(f'/users/login', body=body)
        if user['deleted'] or user['banned']:
            assert resp.status_code == 403
            if user['deleted']:
                assert resp.has_error('The password is correct, but your personal account is deleted.')
            if user['banned']:
                assert resp.has_error('The password is correct, but your personal account is not active.')
        else:
            assert resp.status_code == 200
            assert resp.result
            assert 'token' in resp.result
            # проверим, что такого токена не было до сего момента
            assert resp.result['token'].split('|')[-1] not in ALLTOKENS
            expires = datetime.datetime.strptime(resp.result['expires'][:10], '%Y-%m-%d')
            # проверим, что по умолчанию expires - один месяц
            assert datetime.datetime.date(expires) == datetime.datetime.date(datetime.datetime.now() + datetime.timedelta(days=30))


@pytest.mark.access
def test_put_user_access(api):
    """
    Изменить данные пользователя
    PUT /my
    Тело запроса:
    {
        "name": str,
        "email": str,
        "timezone": str,
        "email_notifications": bool,
        "password": { "old": str,"new": str},
        "settings": { // Тут идёт объект класса UserSettings }
    }
    todo: есть несоответствие с вики. По тестам видно, что никто кроме хозяина не могут изменить юзера.
     В вики - "Обычный пользователь может изменять только свои данные.". Из чего можно предположить, что необычный может
    """
    for _, user in USERS.items():
        for user_id in range(1, 7):
            url = f'/users/{user_id}'
            dataset = datasets['put_users']['1']
            dataset['body']['name'] = f"new_name_for_{user['name']}"
            dataset['body']['email'] = 'new_' + user['email']

            # Описание: пытаемся изменить юзера
            # Параметры: без токена авторизации
            # Ожидаемый результат: только сам юзер, кроме забаненного может себя редактировать
            resp = api.put(url, body=dataset['body'], auth_as=user['email'],
                           query_string=dataset['query_string'])
            if not user['banned'] and user_id == user['id']:
                assert resp.status_code == 200
                assert resp.result

            else:
                assert resp.status_code == 403
                if user['banned']:
                    assert resp.has_error('User banned.')
                else:
                    assert resp.has_error('You can not edit this user.')

        url = f'/my'
        dataset = datasets['put_users']['2']
        dataset['body']['name'] = f"new_name_for_{user['name']}"
        dataset['body']['email'] = user['email']

        # Описание: пытаемся изменить юзера
        # Параметры: без токена авторизации
        # Ожидаемый результат: только сам юзер, кроме забаненного может себя редактировать
        resp = api.put(url, body=dataset['body'], auth_as=user['email'],
                       query_string=dataset['query_string'])
        if not user['banned']:
            assert resp.status_code == 200
            assert resp.result
        else:
            assert resp.status_code == 403
            if user['banned']:
                assert resp.has_error('User banned.')


def test_put_my_good(api):
    """
    PUT /my
    """
    set_flow({'TOKEN': ['1-1.jpg']})
    body = {
        'avatar': 'flow@TOKEN/1-1.jpg',
        'contacts': {
            1: {'type': 'phone', 'value': '+79998887766'},
            2: {'type': 'phone', 'value': '+79998887766', 'sort': -1},
            3: {'type': 'phone', 'value': '+79998887766', 'sort': 1, 'note': 'Звонить после 12'},
            4: {'type': 'link', 'value': 'http://goatse.cx/'},
        }
    }
    resp = api.put('/my', auth_as='anna@biganto.com', body=body)
    assert resp.status_code == 200, f'{resp.object}'
    assert resp.result['avatar']

    body = {
        'avatar': None
    }
    resp = api.put('/my', auth_as='anna@biganto.com', body=body, _debug=True)
    assert resp.status_code == 200, f'{resp.object}'
    assert resp.result['avatar'] is None
    assert resp.result['contacts']


def test_get_my(api):
    resp = api.get('/my', auth_as='anna@biganto.com', _debug=True)
    assert resp.status_code == 200

    fields = [
        'last_active', 'banned', 'stripe_customer_id', 'octobat_customer', 'count_footages', 'purge_timedelta', 'notifications_unseen',
        'plan_id', 'processings_left', 'last_payment_time', 'next_payment_time'
    ]
    qs = {
        'settings': 'nodefault', 
        'fields': ','.join(fields) 
    }
    resp = api.get('/my', auth_as='anna@biganto.com', query_string=qs, _debug=True)
    assert resp.status_code == 200
    assert resp.result['settings'] == {}
    for field in fields:
        assert field in resp.result


@pytest.mark.access
def test_access_users(api):
    for user_id, user in USERS.items():
        # Описание: пытаемся изменить юзера
        # Параметры: без токена авторизации
        # Ожидаемый результат: 403
        resp = api.put(f'/users/{user_id}')
        assert resp.status_code == 403
        # Описание: пытаемся удалить токен авторизации
        # Параметры: без токена авторизации
        # Ожидаемый результат: 401
        body = {'password': '123'}
        resp = api.post(f'/users/{user_id}/delete', body=body)
        assert resp.status_code == 401
        assert resp.has_error('The server could not verify that you are authorized to access the URL requested.')

        # Описание: пытаемся убрать отметку об удалении
        # Параметры: без токена авторизации
        # Ожидаемый результат: 401
        resp = api.post(f'/users/{user_id}/undelete')
        assert resp.status_code == 401
        assert resp.has_error('The server could not verify that you are authorized to access the URL requested.')


def test_delete_undelete_user(api):
    """
    В это модуле протестируем и удаление юзера и восстановление.
    Пометить аккаунт как удалённый
    POST /my/delete
    POST /users/<user_id>/delete
    Тело запроса:
    {
    "password": str
    }

    Восстановить удалённый аккаунт
    POST /my/undelete
    POST /users/<user_id>/undelete
    Тело запроса:
    {
    "password": str
    }
    """
    for user_id, user in USERS.items():
        # Описание: пытаемся убрать отметку об удалении
        # Параметры: с токеном авторизации
        # Ожидаемый результат: только сам юзер, кроме забаненного и уже удаленного может себя удалить,

        body = {'password': '123'}
        resp = api.post(f'/users/{user_id}/delete', auth_as=user['email'], body=body)
        if user['deleted'] or user['banned']:
            assert resp.status_code in (400, 401)
            if user['deleted']:
                assert resp.has_error('Your account is already marked for deletion.')
            if user['banned']:
                assert resp.has_error('The server could not verify that you are authorized to access the URL requested.')
        else:
            assert resp.status_code == 204

        # Описание: пытаемся убрать отметку об удалении
        # Параметры: с токеном авторизации
        # Ожидаемый результат: только сам юзер, кроме забаненного может убрать отметку об удалении
        resp = api.post(f'/users/{user_id}/undelete', auth_as=user['email'],)
        if user['banned']:
            assert resp.status_code in (400, 401)
            assert resp.has_error('The server could not verify that you are authorized to access the URL requested.')
        else:
            assert resp.status_code == 204

        # Описание: пытаемся поставить отметку об удалении
        # Параметры: без токена авторизации
        # Ожидаемый результат: 403
        resp = api.post(f'/my/delete', body=body)
        assert resp.status_code == 401
        assert resp.has_error('The server could not verify that you are authorized to access the URL requested.')

        # Описание: пытаемся поставить отметку об удалении
        # Параметры: с токеном авторизации
        # Ожидаемый результат: только сам юзер, кроме забаненного может убрать поставить отметку об удалении
        resp = api.post(f'/my/delete', auth_as=user['email'], body=body)
        if user['banned']:
            assert resp.status_code in (400, 401)
            if user['banned']:
                assert resp.has_error('The server could not verify that you are authorized to access the URL requested.')
        else:
            assert resp.status_code == 204
        
        resp = api.post(f'/my/undelete')
        assert resp.status_code == 401
        assert resp.has_error('The server could not verify that you are authorized to access the URL requested.')

        # Описание: пытаемся убрать отметку об удалении
        # Параметры: с токеном авторизации
        # Ожидаемый результат: только сам юзер, кроме забаненного может убрать отметку об удалении
        if user['id'] != 6:
            resp = api.post(f'/my/undelete', auth_as=user['email'],)
            if user['banned']:
                assert resp.status_code == 401
                assert resp.has_error('The server could not verify that you are authorized to access the URL requested.')
            else:
                assert resp.status_code == 204


def test_delete_undelete_all_users(api):
    """
    Тестируем удаление юзеров всеми юзерами, включая юзеров с ролями admin, super, user
    """
    for _, user in USERS.items():
        body = {'password': '123'}
        for user_id in range(1, 8):
            # Описание: пытаемся удалить токен авторизации
            # Параметры: тестируем удаление юзеров всеми юзерами, включая юзеров с ролями admin, super, user
            # Ожидаемый результат: только сам юзер, кроме забаненного может себя удалить,
            # роли не могут удалить другого юзера
            resp = api.post(f'/users/{user_id}/delete', auth_as=user['email'], body=body)
            if user_id != user['id'] and user['banned']:
                assert resp.status_code in (401, 403)
                if user['banned']:
                    assert resp.has_error('The server could not verify that you are authorized to access the URL requested')
                else:
                    assert resp.has_error('You can not edit this user.')
        if user['id'] != 6:
            api.post(f'/my/undelete', auth_as=user['email'], )


@pytest.mark.bad_requests
def test_exceptions(api):
    """
    Плохие запросы
    """
    # Описание: Пробуем получить токен авторизации
    # Параметры: нет пароля
    body = {'email': 'anna@biganto.com'}
    resp = api.post('/users/login', body=body)
    assert resp.status_code == 400
    assert resp.has_error('Malformed input data.')

    # Описание: Пробуем получить токен авторизации
    # Параметры: нет логина
    body = {'password': 'password'},
    resp = api.post('/users/login', body=body)
    assert resp.status_code == 400
    assert resp.has_error('Malformed input data.')

    # Описание: Пробуем получить токен авторизации
    # Параметры: нет юзера с таким логином
    body = {'email': 'some@biganto.com', 'password': 'some_pass'}
    resp = api.post('/users/login', body=body)
    assert resp.status_code == 403
    assert resp.has_error('Wrong login.')

    # Описание: Пробуем получить токен авторизации
    # Параметры: не верный пароль
    body = {'email': 'anna2@biganto.com', 'password': 'some_pass'}
    resp = api.post('/users/login', body=body)
    assert resp.status_code == 403
    assert resp.has_error('Wrong password.')

    # Описание: Пробуем получить токен авторизации
    # Параметры: протухшая дата
    expires = datetime.datetime.now() - datetime.timedelta(days=1)
    body = {'email': 'anna2@biganto.com', 'password': '123', 'expires': expires}
    resp = api.post('/users/login', body=body)
    assert resp.status_code == 400
    assert resp.has_error('Requested token expiration time is in past.')

    # Описание: Пробуем получить токен авторизации
    # Параметры: expires не дата
    body = {'email': 'anna2@biganto.com', 'password': '123', 'expires': 'expires'}
    resp = api.post('/users/login', body=body)
    assert resp.status_code == 400
    assert resp.has_error('Malformed expires value.')

    # Описание: Пытаемся изменить юзера
    # Параметры: не валидный email
    body = {'name': 'name', 'email': 123, 'timezone': 'Etc/GMT-3', 'email_notifications': False,
            'settings': {'filincam': {'autoprocess': True}}}
    resp = api.put('/users/7', body=body, auth_as='anna2@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('The email address is not valid.')

    # Описание: Пытаемся изменить юзера
    # Параметры: не валидная таймзона
    body = {'name': 'name', 'anna2@biganto.com': 'timezone', 'timezone': 123, 'email_notifications': False,
            'settings': {'filincam': {'autoprocess': True}}}
    resp = api.put('/users/7', body=body, auth_as='anna2@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Unknown timezone')

    # Описание: Пытаемся изменить юзера
    # Параметры: не существующий юзер
    body = {'name': 'name', 'anna2@biganto.com': 'timezone'}
    resp = api.put('/users/120', body=body, auth_as='anna2@biganto.com')
    assert resp.status_code == 404
    assert resp.has_error('The requested URL was not found on the server.')

    # Описание: Пытаемся пометить на удаление юзера
    # Параметры: не существующий юзер
    resp = api.post('/users/120/delete', body=body, auth_as='anna2@biganto.com')
    assert resp.status_code == 404
    assert resp.has_error('The requested URL was not found on the server.')

    # Описание: Пытаемся пометить на удаление юзера
    # Параметры: Пытаемся удалить чужого юзера - не себ
    resp = api.post('/users/6/delete', body=body, auth_as='anna2@biganto.com')
    assert resp.status_code == 403
    assert resp.has_error('You can not edit this user.')

    # Описание: Пытаемся удалить токен
    # Параметры: нет такого токена
    resp = api.post('/users/logout', query_string={'auth_token': 'auth_token'})
    assert resp.status_code == 401
    assert resp.has_error('Bad auth_token.')


def test_logout_user(api):
    """
    Разавторизация токена
    POST /users/logout
    """
    for user_id, user in USERS.items():
        auth_token = f"X|{TOKENS[user_id]['id']}|{TOKENS[user_id]['signature']}"
        resp = api.post('/users/logout', query_string={'auth_token': auth_token})
        # Описание: пытаемся удалить токен авторизации
        # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может удалить свой токен
        if user['banned']:
            assert resp.status_code == 403
            assert resp.has_error('User banned.')
        else:
            assert resp.status_code == 204
