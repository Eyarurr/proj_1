import os
import datetime

import pytest

from visual import create_app
from visual.core import db
from visual.models import User, Footage, Tour, TeamMember, AuthToken
import shutil

USERS = {}
TOURS = {}

datasets = {'get_qr': [
    {'id': 1,
     'query_string': {'error_correction': 'L', 'version': 20, 'format': 'svg', 'border_size': 5,
                      'scale': 5, 'rebuild_cache': 0, 'return': 'url'}
     },
    {'id': 2,
     'query_string': {'error_correction': 'L', 'version': 20, 'format': 'svg', 'border_size': 5,
                      'scale': 5, 'rebuild_cache': 0, 'return': 'content'}
     },
    {'id': 3,
     'query_string': {'error_correction': 'L', 'version': 20, 'format': 'svg', 'border_size': 5,
                      'scale': 5, 'rebuild_cache': 1, 'return': 'content'}
     }, ]
}


def setup_module():
    """
    Добавляем 6 юзеров, 1, 2, 3, 6 - нормальные, 4 - забаненный и 5 - удалённый
    Всем, кроме 6 добавляем подписку virtoaster-trial
    Создаем по одному туры каждому юзеру
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.expire_on_commit = False
        qr_dir = app.config.get('QR_DIR')
        shutil.rmtree(qr_dir, ignore_errors=True)
        os.makedirs(qr_dir, exist_ok=True)
        users = [
            {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com'},
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
            if user.id != 6:
                user.set_virtoaster_plan(0)
            tour = Tour(id=user.id, user_id=user.id, title='tour',
                        footage=Footage(user_id=user.id, _status='testing', type='real'))
            db.session.add(tour)
            db.session.flush()

            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title')}

        db.session.commit()
        db.session.close()


def test_get_qr_default(api):
    """
    Получить QR-код со ссылкой на плеер тура
    GET /tours/<int:tour_id>/qr
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = user_id

        # Пытаемся получить qr тура с параметрами по умолчанию без авторизации.
        # Ожидаемый результат: Можно получить qr любого тура кроме забаненного удаленного и
        # без подписки 'virtoaster'
        resp = api.get(f'/tours/{tour_id}/qr')
        if user['id'] not in (4, 5, 6):
            assert resp.status_code == 200
            assert 'url' in resp.object['result']
        else:
            assert resp.status_code == 403

        # Пытаемся получить qr тура с параметрами по умолчанию с авторизацией.
        # Ожидаемый результат: Любой юзер, кроме забаненного может получить qr своего тура
        resp = api.get(f'/tours/{tour_id}/qr', auth_as=user['email'], _debug=True)
        if not user['banned']:
            assert resp.status_code == 200
            assert 'url' in resp.object['result']
        else:
            assert resp.status_code == 403


def test_get_qr(api):
    """
    Получить QR-код со ссылкой на плеер тура
    GET /tours/<int:tour_id>/qr
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        for dataset in datasets['get_qr']:
            tour_id = user_id
            # Пытаемся получить qr тура.
            # Параметры: Передаем query_string
            # Ожидаемый результат: Можно получить qr любого тура, кроме тура в статусе banned
            # и туры забаненного и удаленного юзера
            resp = api.get(f'/tours/{tour_id}/qr', query_string=dataset['query_string'], auth_as=user['email'],
                           )
            if not user['banned']:
                assert resp.status_code == 200
                if dataset['query_string']['return'] == 'url':
                    assert 'url' in resp.object['result']
                if dataset['query_string']['return'] == 'content':
                    assert 'attachment;' in resp.headers['Content-Disposition']
            else:
                assert resp.status_code == 403


@pytest.mark.bad_requests
def test_exception(api):
    """
    Плохие запросы
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        for dataset in datasets['get_qr']:
            tour_id = user_id
            # error_correction не из  ('L', 'M', 'Q', 'H')
            query_string_tmp = dataset['query_string'].copy()
            query_string_tmp['error_correction'] = 'G'
            resp = api.get(f'/tours/{tour_id}/qr', query_string=query_string_tmp, auth_as=user['email'])
            if not user['banned']:
                assert resp.status_code == 400
                resp.has_error('Malformed error_correction value.')
            else:
                assert resp.status_code == 403

            # version не (1, 40)
            query_string_tmp = dataset['query_string'].copy()
            query_string_tmp['version'] = 50
            resp = api.get(f'/tours/{tour_id}/qr', query_string=query_string_tmp, auth_as=user['email'])
            if not user['banned']:
                assert resp.status_code == 400
                resp.has_error('Malformed error_correction value.')
            else:
                assert resp.status_code == 403

            # format не ('png', 'svg')
            query_string_tmp = dataset['query_string'].copy()
            query_string_tmp['format'] = 'wsvg'
            resp = api.get(f'/tours/{tour_id}/qr', query_string=query_string_tmp, auth_as=user['email'])
            if not user['banned']:
                assert resp.status_code == 400
                resp.has_error('Malformed error_correction value.')
            else:
                assert resp.status_code == 403

            # scale не целое число
            query_string_tmp = dataset['query_string'].copy()
            query_string_tmp['scale'] = 'some_'
            resp = api.get(f'/tours/{tour_id}/qr', query_string=query_string_tmp, auth_as=user['email'])
            if not user['banned']:
                assert resp.status_code == 400
                resp.has_error('Malformed error_correction value.')
            else:
                assert resp.status_code == 403

            # scale не дробь
            query_string_tmp = dataset['query_string'].copy()
            query_string_tmp['scale'] = 'some_'
            resp = api.get(f'/tours/{tour_id}/qr', query_string=query_string_tmp, auth_as=user['email'])
            if not user['banned']:
                assert resp.status_code == 400
                resp.has_error('Malformed error_correction value.')
            else:
                assert resp.status_code == 403
