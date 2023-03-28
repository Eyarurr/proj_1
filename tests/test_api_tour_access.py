"""
Здесь проверяется работа с правами доступа к турам и съёмкам методами:

GET /tours/<id>
GET /footages/<id>
GET /tours
PUT /tours/<id>
PUT /footages/<id>
POST /tours
POST /tours/<id>/copy

Методы запускаются от разных юзеров в отношении разных туров. Проверяется только код возврата и для POST/PUT-методов,
сама изменяемая сущность чтобы проверить, отработал ли метод, или отдал HTTP 200 не поменяв ничего.
"""
import datetime

from visual import create_app
from visual.core import db
from visual.models import User, TeamMember, AuthToken, Tour, Footage


def setup_module():
    """
    Создаёт в пустой базе юзеров:
    1. anna@biganto.com без ролей
    2. boris@biganto.com с ролями ('gallery')
    3. cidor@biganto.com с ролями ('tours')
    4. banned@biganto.com c User.banned = True и ролью ('tours')
    6. deleted@biganto.com с User.deleted != None и ролью ('tours')

    Каждому даёт по токену авторизации токену, равному User.email.

    Каждому юзеру создаются пары съёмка-тур:
    user_id*10:   'Simple'
    user_id*10+1: 'Hidden': Tour.hidden = True
    user_id*10+2: 'Banned': Footage.status = 'banned'
    user_id*10+3: 'Password': Tour.password_hash = hash('qwerty')
    :return:
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()

        users = [
            User(id=1, email='anna@biganto.com', email_confirmed=True),
            User(id=2, email='boris@biganto.com', email_confirmed=True, team_member=TeamMember(roles=['gallery'])),
            User(id=3, email='cidor@biganto.com', email_confirmed=True, team_member=TeamMember(roles=['tours'])),
            User(id=4, email='banned@biganto.com', email_confirmed=True, banned=True, team_member=TeamMember(roles=['tours'])),
            User(id=6, email='deleted@biganto.com', email_confirmed=True, deleted=datetime.datetime.now(), team_member=TeamMember(roles=['tours'])),
        ]
        for user in users:
            user.auth_tokens.append(AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30), ip='0.0.0.0'))
            db.session.add(user)
            db.session.flush()
            user.set_virtoaster_plan(0)

            id_ = user.id * 10
            t = Tour(id=id_, user_id=user.id, title='Simple', footage=Footage(id=id_, user_id=user.id, type='virtual', _status='published'))
            db.session.add(t)

            id_ = user.id * 10 + 1
            t = Tour(id=id_, user_id=user.id, title='Hidden', hidden=True, footage=Footage(id=id_, user_id=user.id, type='virtual', _status='published'))
            db.session.add(t)

            id_ = user.id * 10 + 2
            t = Tour(id=id_, user_id=user.id, title='Banned', footage=Footage(id=id_, user_id=user.id, type='virtual', _status='banned'))
            db.session.add(t)

            id_ = user.id * 10 + 3
            t = Tour(id=id_, user_id=user.id, title='Password', password_hash=Tour.hash_password('qwerty'), footage=Footage(id=id_, user_id=user.id, type='virtual', _status='published'))
            db.session.add(t)

        # Так как мы руками ставили значения tours.id и footages.id, секвенция не изменилась, и при вставке новой строки в tours или footages
        # произойдёт нарушение уникальности первичного ключа.
        db.session.execute("SELECT setval('tours_id_seq', 100)")
        db.session.execute("SELECT setval('footages_id_seq', 100)")

        db.session.commit()


def test_tour_access_get(api):
    # Список запросов GET /tours/<tour_id>:
    # username: {
    #   tour_id: status_code, ...
    # }
    matrix = {
        None: {
            10: 200, 11: 403, 12: 403, 13: 403,
            20: 200, 21: 403, 22: 403, 23: 403,
            30: 200, 31: 403, 32: 403, 33: 403,
            40: 403, 41: 403, 42: 403, 43: 403,
            60: 403, 61: 403, 62: 403, 63: 403
        },
        'anna@biganto.com': {
            10: 200, 11: 200, 12: 200, 13: 200,
            20: 200, 21: 403, 22: 403, 23: 403,
            30: 200, 31: 403, 32: 403, 33: 403,
            40: 403, 41: 403, 42: 403, 43: 403,
            60: 403, 61: 403, 62: 403, 63: 403
        },
        'boris@biganto.com': {
            10: 200, 11: 403, 12: 403,
            20: 200, 21: 200, 22: 200,
            30: 200, 31: 403, 32: 403,
            40: 403, 41: 403, 42: 403,
            60: 403, 61: 403, 62: 403,
        },
        'cidor@biganto.com': {
            10: 200, 11: 200, 12: 200, 13: 200,
            20: 200, 21: 200, 22: 200, 23: 200,
            30: 200, 31: 200, 32: 200,
            40: 200, 41: 200, 42: 200,
            60: 200, 61: 200, 62: 200,
        },
        'banned@biganto.com': {
            10: 200, 11: 403, 12: 403,
            20: 200, 21: 403, 22: 403,
            30: 200, 31: 403, 32: 403,
            40: 403, 41: 403, 42: 403,
            60: 403, 61: 403, 62: 403,
        },
        'deleted@biganto.com': {
            10: 200, 11: 403, 12: 403,
            20: 200, 21: 403, 22: 403,
            30: 200, 31: 403, 32: 403,
            40: 403, 41: 403, 42: 403,
            60: 200, 61: 200, 62: 200,
        },
    }
    for username, tests in matrix.items():
        for tour_id, expected_status in tests.items():
            resp = api.get('/tours/{}'.format(tour_id), auth_as=username)
            assert resp.status_code == expected_status, 'User {}: GET /tours/{}: {}'.format(username, tour_id, resp)


def test_footage_access_get(api):
    # Список запросов GET /footages/<tour_id>:
    # username: {
    #   tour_id: status_code, ...
    # }
    matrix = {
        None: {
            10: 200, 12: 403,
            20: 200, 22: 403,
            30: 200, 32: 403,
            40: 403, 42: 403,
            60: 403, 62: 403,
        },
        'anna@biganto.com': {
            10: 200, 12: 200,
            20: 200, 22: 403,
            30: 200, 32: 403,
            40: 403, 42: 403,
            60: 403, 62: 403,
        },
        'boris@biganto.com': {
            10: 200, 12: 403,
            20: 200, 22: 200,
            30: 200, 32: 403,
            40: 403, 42: 403,
            60: 403, 62: 403,
        },
        'cidor@biganto.com': {
            10: 200, 12: 200,
            20: 200, 22: 200,
            30: 200, 32: 200,
            40: 200, 42: 200,
            60: 200, 62: 200,
        },
        'banned@biganto.com': {
            10: 200, 12: 403,
            20: 200, 22: 403,
            30: 200, 32: 403,
            40: 403, 42: 403,
            60: 403, 62: 403,
        },
        'deleted@biganto.com': {
            10: 200, 12: 403,
            20: 200, 22: 403,
            30: 200, 32: 403,
            40: 403, 42: 403,
            60: 200, 62: 200,
        },
    }
    for username, tests in matrix.items():
        for footage_id, expected_status in tests.items():
            resp = api.get('/footages/{}'.format(footage_id), auth_as=username)
            assert resp.status_code == expected_status, 'User {}: GET /footages/{}: {}'.format(username, footage_id, resp)


def test_tour_access_get_all(api):
    """
    Проверяет загрузку всех туров пользователя.
    :param api:
    :return:
    """
    # auth_as: {user_id: [expected tour ids] или HTTP-статус}
    matrix = {
        None: {
            1: {10, 13},
            2: {20, 23},
            3: {30, 33},
            4: 403,
            6: 404
        },
        'anna@biganto.com': {
            1: {10, 11, 12, 13},
            2: {20, 23},
            3: {30, 33},
            4: 403,
            6: 404
        },
        'boris@biganto.com': {
            1: {10, 13},
            2: {20, 21, 22, 23},
            3: {30, 33},
            4: 403,
            6: 404
        },
        'cidor@biganto.com': {
            1: {10, 11, 12, 13},
            2: {20, 21, 22, 23},
            3: {30, 31, 32, 33},
            4: {40, 41, 42, 43},
            6: {60, 61, 62, 63}
        },
        'banned@biganto.com': {
            1: {10, 13}, 2: {20, 23}, 3: {30, 33}, 4: 403, 6: 404
        },
        'deleted@biganto.com': {
            1: {10, 13}, 2: {20, 23}, 3: {30, 33}, 4: 403, 6: 404
        }
    }
    for auth_as, tests in matrix.items():
        for user_id, expected_tours in tests.items():
            resp = api.get('/tours', query_string={'user_id': user_id, 'fields': 'id'}, auth_as=auth_as)
            assert_str = 'User {}: GET /tours {{user_id: {}}}, expect {}: {}'.format(auth_as, user_id, expected_tours, resp)
            if type(expected_tours) is int:
                assert resp.status_code == expected_tours, assert_str
            else:
                assert resp.status_code == 200, assert_str
                ids = [_['id'] for _ in resp.result]
                assert set(ids) == expected_tours, assert_str


def test_tour_access_put(api):
    # Список запросов PUT /tours/<tour_id>:
    # username: {
    #   tour_id: status_code, ...
    # }
    matrix = {
        None: {
            10: 403, 11: 403, 12: 403,
            20: 403, 21: 403, 22: 403,
            30: 403, 31: 403, 32: 403,
            40: 403, 41: 403, 42: 403,
            60: 403, 61: 403, 62: 403,
        },
        'anna@biganto.com': {
            10: 200, 11: 200, 12: 200,
            20: 403, 21: 403, 22: 403,
            30: 403, 31: 403, 32: 403,
            40: 403, 41: 403, 42: 403,
            60: 403, 61: 403, 62: 403,
        },
        'boris@biganto.com': {
            10: 403, 11: 403, 12: 403,
            20: 200, 21: 200, 22: 200,
            30: 403, 31: 403, 32: 403,
            40: 403, 41: 403, 42: 403,
            60: 403, 61: 403, 62: 403,
        },
        'cidor@biganto.com': {
            10: 200, 11: 200, 12: 200,
            20: 200, 21: 200, 22: 200,
            30: 200, 31: 200, 32: 200,
            40: 200, 41: 200, 42: 200,
            60: 200, 61: 200, 62: 200,
        },
        # Действия от забаненного юзера можно и не проверять, так как у него не получится авторизоваться
        'banned@biganto.com': {
            10: 403, 11: 403, 12: 403,
            20: 403, 21: 403, 22: 403,
            30: 403, 31: 403, 32: 403,
            40: 403, 41: 403, 42: 403,
            60: 403, 61: 403, 62: 403,
        },
        'deleted@biganto.com': {
            10: 403, 11: 403, 12: 403,
            20: 403, 21: 403, 22: 403,
            30: 403, 31: 403, 32: 403,
            40: 403, 41: 403, 42: 403,
            60: 200, 61: 200, 62: 200,
        },
    }
    for username, tests in matrix.items():
        for tour_id, expected_status in tests.items():
            body = {'meta': {'teststamp': 'modified {} / tour_id'.format(username, tour_id)}}
            resp = api.put('/tours/{}'.format(tour_id), body, auth_as=username)
            assert resp.status_code == expected_status, 'User {}: PUT /tours/{}: {}'.format(username, tour_id, resp)


def test_footage_access_put(api):
    # Список запросов PUT /footages/<tour_id>:
    # username: {
    #   tour_id: status_code, ...
    # }
    matrix = {
        None: {
            10: 403, 12: 403,
            20: 403, 22: 403,
            30: 403, 32: 403,
            40: 403, 42: 403,
            60: 403, 62: 403,
        },
        'anna@biganto.com': {
            10: 200, 12: 200,
            20: 403, 22: 403,
            30: 403, 32: 403,
            40: 403, 42: 403,
            60: 403, 62: 403,
        },
        'boris@biganto.com': {
            10: 403, 12: 403,
            20: 200, 22: 200,
            30: 403, 32: 403,
            40: 403, 42: 403,
            60: 403, 62: 403,
        },
        'cidor@biganto.com': {
            10: 200, 12: 200,
            20: 200, 22: 200,
            30: 200, 32: 200,
            40: 200, 42: 200,
            60: 200, 62: 200,
        },
        # Действия от забаненного юзера можно и не проверять, так как у него не получится авторизоваться
        'banned@biganto.com': {
            10: 403, 12: 403,
            20: 403, 22: 403,
            30: 403, 32: 403,
            40: 403, 42: 403,
            60: 403, 62: 403,
        },
        'deleted@biganto.com': {
            10: 403, 12: 403,
            20: 403, 22: 403,
            30: 403, 32: 403,
            40: 403, 42: 403,
            60: 200, 62: 200,
        },
    }
    for username, tests in matrix.items():
        for footage_id, expected_status in tests.items():
            body = {'meta': {'teststamp': 'modified {} / tour_id'.format(username, footage_id)}}
            resp = api.put('/footages/{}'.format(footage_id), body, auth_as=username)
            assert resp.status_code == expected_status, 'User {}: PUT /footages/{}: {}'.format(username, footage_id, resp)


def test_tour_access_post(api):
    """
    Проверяет создание туров методом POST /tours одними юзерами другим юзерам.
    :param api:
    :return:
    """
    # username: { request.body.user_id => expected tour.user_id }
    # expected = None — тур не должен создастся
    matrix = {
        'anna@biganto.com': {
            None: 1, 1: 1, 2: None, 3: None,
        },
        'boris@biganto.com': {
            None: 2, 1: None, 2: 2, 3: None
        },
        'cidor@biganto.com': {
            None: 3, 1: 1, 2: 2, 3: 3
        },
        'banned@biganto.com': {
            None: None, 1: None, 2: None, 3: None
        },
        'deleted@biganto.com': {
            None: None, 1: None, 2: None, 3: None
        }
    }

    for username, tests in matrix.items():
        for user_id, expected_user_id in tests.items():
            body = {
                'user_id': user_id,
                'footage_id': 10
            }
            resp = api.post('/tours', body, auth_as=username)
            assert_str = 'User {}: POST /tours {{user_id: {}}}: {}'.format(username, user_id, resp)
            if expected_user_id is None:
                assert resp.status_code == 403, assert_str
            else:
                assert resp.status_code == 200, assert_str


def test_tour_access_copy(api):
    """
    Проверяет копирование туров методом POST /tours/<id>/copy
    :param api:
    :return:
    """
    # Копируем как свой, так и чужой тур другим юзерам
    # auth_as: {tour_id: {request.body.user_id => expected tour.user_id}}
    # expected = None - тур не должен копироваться
    matrix = {
        'anna@biganto.com': {
            10: {None: 1, 1: 1, 2: None, 3: None},
            20: {None: None, 1: None, 2: None, 3: None}
        },
        'boris@biganto.com': {
            20: {None: 2, 1: None, 2: 2, 3: None}
        },
        'cidor@biganto.com': {
            30: {None: 3, 1: 1, 2: 2, 3: 3},
            10: {None: 3, 1: 1, 2: 2, 3: 3}
        },
        'banned@biganto.com': {
            40: {None: None, 1: None, 2: None, 3: None},
            10: {None: None, 1: None, 2: None, 3: None}
        },
        'deleted@biganto.com': {
            60: {None: None, 1: None, 2: None, 3: None},
            10: {None: None, 1: None, 2: None, 3: None}
        }
    }

    for auth_as, tests in matrix.items():
        for tour_id, responses in tests.items():
            for user_id, expected_user_id in responses.items():
                body = {
                    'user_id': user_id,
                }
                resp = api.post('/tours/{}/copy'.format(tour_id), body, auth_as=auth_as)
                
                assert_str = 'User {}: POST /tours/{}/copy {{user_id: {}}}, expect {}: {}'.format(auth_as, tour_id, user_id, expected_user_id, resp)
                if expected_user_id is None:
                    assert resp.status_code == 403, assert_str
                else:
                    assert resp.status_code == 200, assert_str


def test_tour_passwords(api):
    """
    Проверяем доступ к чужому запароленному туру с паролем или хешем пароля, как правильным, так и неправильным
    :param api:
    :return:
    """
    resp = api.get('/tours/13', auth_as=None)
    assert resp.status_code == 403
    assert resp.headers.get('X-Reason') == 'password'

    resp = api.get('/tours/13', query_string={'password': 'wrong'}, auth_as=None)
    assert resp.status_code == 403
    assert resp.headers.get('X-Reason') == 'password'

    resp = api.get('/tours/13', query_string={'password': 'qwerty'}, auth_as=None)
    assert resp.status_code == 200

    resp = api.get('/tours/13', query_string={'password_hash': 'wrong'}, auth_as=None)
    assert resp.status_code == 403
    assert resp.headers.get('X-Reason') == 'password'

    resp = api.get('/tours/13', query_string={'password_hash': '3a40f56609c5fbb55a92ce4ab9cb4fb3'}, auth_as=None)
    assert resp.status_code == 200
