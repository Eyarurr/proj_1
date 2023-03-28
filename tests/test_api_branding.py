import datetime

import datauri
import pytest

from tests.common import set_flow
from visual import create_app
from visual.core import db
from visual.models import TourPaidFeature, User, Footage, Tour, TeamMember, AuthToken
from .conftest import SRC_DIR

FILE_DATA_URI = datauri.DataURI.from_file(SRC_DIR + '/256x256.jpg')

datasets = {
    'branding_put': [
        {'id': 1, 'title': 'branding_put', 'description': '',
         'body': {'copyright_map': 'Подпись над миникартой', 'copyright_help': 'Подпись в справке',
                  'logo_help@flow': 'TOKEN/256x256.jpg', 'logo_help_link': 'https://ya.ru',
                  },
         },
        {'id': 11, 'title': 'branding_put', 'description': 'logo_help flow@TOKEN',
         'body': {'copyright_map': 'Подпись над миникартой', 'copyright_help': 'Подпись в справке',
                  'logo_help': 'flow@TOKEN/256x256.jpg', 'logo_help_link': 'https://ya.ru',
                  },
         },
        {'id': 12, 'title': 'branding_put', 'description': 'logo_help dataurl',
         'body': {'copyright_map': 'Подпись над миникартой', 'copyright_help': 'Подпись в справке',
                  'logo_help': 'dataurl@' + FILE_DATA_URI, 'logo_help_link': 'https://ya.ru',},
         },
        {'id': 2, 'title': 'branding_put', 'description': 'watermark flow',
         'body': {'watermark': {"url": 'flow@TOKEN/256x256.jpg', 'position': 'center', 'opacity': 0.3}},
         },
        {'id': 21, 'title': 'branding_put', 'description': 'watermark datauri',
         'body': {'watermark': {"url": 'dataurl@' + FILE_DATA_URI}, 'position': None, 'opacity': None},
         },
        {'id': 3, 'title': 'branding_put', 'description': 'очищает брендинг',
         'body': {'watermark': None, 'copyright_map': None, 'copyright_help': None, 'logo_help@flow': None,
                  'logo_help_link': None,},
         },
    ],
    'bad_requests': [
        {'id': 1,
         'body': {'copyright_map': 'Подпись над миникартой', 'copyright_help': 'Подпись в справке',
                  'logo_help_disabled': False, 'logo_help@flow': 'TOKEN/300x300.jpg',
                  'logo_help_link': 'https://ya.ru',
                  },
         },
    ],
}

USERS = {}
TOURS = {}


def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3 - нормальные, 4 - забаненный и 5 - удалённый
    Всем юзерам добавим тарифный план Business. Всем кроме юзера nna@biganto.com добавим фичу branding
    """
    app = create_app('config.test.py')
    global FILE_DATA_URI
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
            # Добавим тариф и фичу
            user.plan_id = 30
            if tour.id != 1:
                feature = TourPaidFeature(tour_id=tour.id, feature='branding')
                db.session.add(feature)
            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title')}

        db.session.commit()
        db.session.close()


def test_put_branding(api):
    """
    Брендинг
    PUT /tours/<tour_id>branding
    тело запроса
    {
        "copyright_map": str,   // Подпись над миникартой
        "copyright_help": str,  // Подпись в справке
        "logo_help@flow": "TOKEN/filename"  // Загрузка кастомного логотипа. Если указать null, то кастомный логотип будет удалён и вернётся дефолтный.
        "logo_help@resize": [w, h],     // Ресайз логотипа при загрузке
        "logo_help_disabled": bool      // Не показы ать логотип вообще (ни кастомный, ни дефолтный)
        "logo_help_link": str           // Ссылка на логотипе
        "watermark" : dict              // Водяной знак
    }
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['branding_put']:
            # Описание: Попытка изменить фичу
            # Параметры: Нет токена авторизации
            # Ожидаемый ответ: 403
            resp = api.put(f'/tours/{tour_id}/branding')
            assert resp.status_code == 403

            # Описание: Попытка изменить фичу
            # Параметры: Есть токен авторизации
            # Ожидаемый ответ: Изменить фичу может любой авторизированный юзер, кроме забаненного юзера и у кого не куплена фича
            set_flow({'TOKEN': ['src/256x256.jpg']})
            if dataset['id'] != 1:
                continue
            resp = api.put(f'/tours/{tour_id}/branding', body=dataset['body'], auth_as=user['email'])
            if user['banned'] or user['email'] == 'anna@biganto.com':
                assert resp.status_code == 403
            else:
                assert resp.status_code == 200


@pytest.mark.bad_requests
def test_exception(api):
    """
    Плохие запросы
    """
    user_id = 3
    user = USERS[user_id]
    tour_id = user_id
    body = {'watermark': {"url": 'flow@TOKEN/256x256.jpg', 'position': 'top', 'opacity': 0.3}}
    resp = api.put(f'/tours/{tour_id}/branding', body=body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error('Invalid "position" value')

    body = {'watermark': {"url": 'flow@TOKEN/256x256.jpg', 'position': None, 'opacity': 10}}
    resp = api.put(f'/tours/{tour_id}/branding', body=body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error('Invalid "opacity" value')

    body = {'watermark': 'string'}
    resp = api.put(f'/tours/{tour_id}/branding', body=body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error('Invalid "watermark" value')

    body = {'watermark': {"url": 'flow@TO/256x256.jpg'}}
    resp = api.put(f'/tours/{tour_id}/branding', body=body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error('Source file TO/256x256.jpg not found for url.')

    body = {'watermark': {"url": 'dataurl@TO/256x256.jpg'}}
    resp = api.put(f'/tours/{tour_id}/branding', body=body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error('Malformed url value. Not a valid data URI: DataURI')

    body = {'watermark': {"url": 'TOKEN/256x256.jpg'}}
    resp = api.put(f'/tours/{tour_id}/branding', body=body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error('Malformed url value.')

    body = {'watermark': {"url": 'flow256x256.jpg'}}
    resp = api.put(f'/tours/{tour_id}/branding', body=body, auth_as=user['email'])
    assert resp.status_code == 400
    assert resp.has_error('Malformed url value.')

    for dataset in datasets['bad_requests']:
        # Описание: Попытка изменить фичу
        # Параметры: в TOKEN не добавлен нужный файл
        # Ожидаемый результат: 400
        resp = api.put(f'/tours/{tour_id}/branding', body=dataset['body'], auth_as=user['email'])
        assert resp.status_code == 400
        assert resp.has_error('Source file TOKEN/300x300.jpg not found for logo_help@flow.')

        # Описание: Попытка изменить фичу
        # Параметры: удаляем logo_help@flow и добавим произвольное свойство
        # Ожидаемый результат: 200 и warning
        del dataset['body']['logo_help@flow']
        dataset['body']['some_prop'] = 'some_val'
        resp = api.put(f'/tours/{tour_id}/branding', body=dataset['body'], auth_as=user['email'])
        assert resp.status_code == 200
        assert resp.has_warning('Unknown input property some_prop')
