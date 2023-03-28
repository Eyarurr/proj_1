'''

'''
import datetime
import json
import pytest

from tests.common import set_flow
from visual import create_app
from visual.core import db
from visual.models import User, AuthToken, Tour, Footage

USERS = {}
TOURS = {}


def setup_module():
    """
    Добавим пять пользователей. Добавляем 5 юзеров, 1, 2, 3 - нормальные, 4 - забаненный и 5 - удалённый
    Всем добавим токены авторизации. У rotten@biganto.com токен протухший (с истекшим сроком)
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        users = [
            {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com'},
            {'id': 2, 'name': 'super', 'email': 'super@biganto.com', 'password_hash': User.hash_password('123')},
            {'id': 3, 'name': 'rotten', 'email': 'rotten@biganto.com'},
            {'id': 4, 'name': 'banned', 'email': 'banned@biganto.com', 'banned': True},
            {'id': 5, 'name': 'deleted', 'email': 'deleted@biganto.com', 'password_hash': User.hash_password('123'),
             'deleted': datetime.datetime.now() - datetime.timedelta(days=1)}
        ]
        for kwargs in users:
            user = User(email_confirmed=True, **kwargs)
            expires = datetime.datetime.now() + datetime.timedelta(days=30) if user.id != 3 \
                else datetime.datetime.now() - datetime.timedelta(days=30)

            params = {'signature': user.email, 'expires': expires, 'ip': '0.0.0.0'}
            user.auth_tokens.append(AuthToken(**params))

            db.session.add(user)
            db.session.flush()
            tour = Tour(user_id=user.id, title='tour',
                        footage=Footage(user_id=user.id, _status='published', type='real'),
                        )
            db.session.add(tour)
            db.session.flush()
            tour.mkdir()
            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title')}
        db.session.commit()
        db.session.close()


def test_auth_token(api):
    """
    Проверяем авторизацию через токен на примере добавления аудио клипа
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        body = {'url@flow': 'TOKEN/main.mp3', 'volume': 1, 'pause': 2, 'loop': True}

        # Параметры: без токена авторизации
        # Ожидаемый результат: 403
        set_flow({'TOKEN': ['src/tours/main.mp3']})
        resp = api.put(f'/tours/{tour_id}/audio/track_2', body=body)
        assert resp.status_code == 403

        # Параметры: с токеном авторизации
        # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного и юзера с протухшим токеном
        # может добавить клип
        set_flow({'TOKEN': ['src/tours/main.mp3']})
        resp = api.put(f'/tours/{tour_id}/audio/track_2', auth_as=user['email'], body=body)
        if user['banned']:
            assert resp.status_code == 403
            assert resp.has_error('User banned.')
        elif user['email'] == 'rotten@biganto.com':
            assert resp.status_code == 401
            assert resp.has_error('Token is invalid.')
        else:
            assert resp.status_code == 200


@pytest.fixture()
def client_api2():
    app = create_app('config.test.py')
    with app.test_client() as client:
        yield client


def test_auth_api2(client_api2):
    """
    api 2.0
    """
    # Получим токен авторизации
    url = 'http://local.biganto.com/api'
    API_QS = {'client': 'web', 'client_version': '1.0', 'v': '2.0', 'estate_id': '0', 'user_id': '1'}
    rv = client_api2.post(f'{url}/users.authorize', data={'email': 'super@biganto.com', 'password': '123'},
                          query_string=API_QS)
    resp = json.loads(rv.get_data(as_text=True))
    assert rv.status_code == 200
    API_QS.update({'auth_token': resp['token']})

    # Проверяем авторизацию через токен на примере на получение списка туров для юзера
    # Параметры: с токеном авторизации
    # Ожидаемый результат: Юзер с токеном может получить список туров
    rv = client_api2.get(f'{url}/tours.getList', query_string=API_QS)
    resp = json.loads(rv.get_data(as_text=True))
    assert rv.status_code == 200
    assert resp

    # Проверяем авторизацию через токен на примере на получение списка туров для юзера
    # Параметры: без токена авторизации
    # Ожидаемый результат:
    del API_QS['auth_token']
    rv = client_api2.get(f'{url}/tours.getList', query_string=API_QS)
    resp = json.loads(rv.get_data(as_text=True))
    assert resp.get('errors')
    assert resp.get('errors')[0].get('message') == 'Please authorize.'
