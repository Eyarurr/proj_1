import os

import json
import datetime

import pytest

from tests.common import set_flow
from tests.conftest import SRC_DIR
from visual import create_app
from visual.core import db, products
from visual.models import User, Footage, Tour, AuthToken, TeamMember, UserProduct
from sqlalchemy.orm.attributes import flag_modified

with open(os.path.join(SRC_DIR, 'meta_loading.json')) as fm:
    meta_loading = json.load(fm)

datasets = {
    'put_skyboxes': [
        {'id': 1,
         'description': 'Добавляем панорамы в тур',
         'body': {"upload_token": "TOKEN", "binocular": False
                  },
         },
        {'id': 2,
         'description': 'Добавляем бинокулярные панорамы в тур',
         'body': {"upload_token": "TOKEN", "binocular": True
                  },
         },
    ],
    'put_skybox': [
        {'id': 1,
         'description': 'Сохраняем панорамы в тур',
         'body': {'pos': [1, 2, 3], 'q': [1, 2, 3, 4], 'file_name@flow': "TOKEN/panorama1536.png",
                  'lr_file_name@flow': "TOKEN/panorama_bin_1536.png"
                  },
         'verify_description': ''},
        {'id': 2,
         'description': 'Сохраняем панорамы в тур',
         'body': {'pos': [1, 2, 3], 'q': [1, 2, 3, 4], 'file_name@flow': "TOKEN/panorama.png",
                  'lr_file_name@flow': "TOKEN/panorama_binocular.png"
                  },
         'verify_description': ''},
        {'id': 3,
         'description': 'Сохраняем панорамы в тур',
         'body': {'pos': [1, 2, 3], 'q': [1, 2, 3, 4], 'file_name@flow': "TOKEN/panorama2048.png",
                  'lr_file_name@flow': "TOKEN/panorama_bin_2048.png"
                  },
         'verify_description': ''}
    ],
    'put_model': [
        {'id': 1,
         'description': 'Добавляем модель',
         'body': {'model@flow': "TOKEN/model-0.obj",
                  },
         'verify_description': ''},
    ],
    'bad_requests': {
        'bad_model': {'description': 'Добавляем модель, у файла не obj расширение',
                      'body': {'model@flow': "TOKEN/tours.json",
                               }},
        'max_res': {'description': 'Расширение файлов != 1536',
                    'body': {'pos': [1, 2, 3], 'q': [1, 2, 3, 4], 'file_name@flow': "TOKEN/panorama2048.png",
                             'lr_file_name@flow': "TOKEN/panorama_bin_2048.png"
                             }},
    },
}

USERS = {}
TOURS = {}
# Каким юзерам добавили продукт virtoaster
PLAN_IDS = {1: 0, 2: 20, 3: 30}

def setup_module():
    """
    Добавим пять юзеров из них 4 - забанен, 5 - удален, у 1, 2 и 3 plan_id 0, 20 и 30 соответственно.
    Для каждого юзера добавим по два тура и две съемки. В мету съемки добавим meta_loading. В съемки id > 10 добавим
    параметр 'max_resolution' = 2048
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.expire_on_commit = False
        users = [
            {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com'},
            {'id': 2, 'name': 'boris', 'email': 'boris@biganto.com', 'team_member': TeamMember(roles=['tours'])},
            {'id': 3, 'name': 'super', 'email': 'super@biganto.com', 'team_member': TeamMember(roles=['super']), 'password_hash': User.hash_password('123')},
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
            if user.id in PLAN_IDS.keys():
                plan_id = PLAN_IDS[user.id]
                db.session.add(UserProduct(user_id=user.id, product_id = 'virtoaster', plan_id=plan_id, meta={'processings_left': 3}))
            for i in range(0, 11, 10):
                tour = Tour(id=user.id + i, user_id=user.id, title='tour',
                            footage=Footage(id=user.id + i, user_id=user.id, _status='loading', type='virtual', meta=meta_loading))
                db.session.add(tour)
                db.session.flush()
                tour.mkdir()
                tour.footage.mkdir()
                USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
                TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title')}

        # Добавим в мету 'max_resolution' = 2048
        footages = Footage.query.filter(Footage.id > 10).all()
        for footage in footages:
            footage.meta['_loading']['options']['max_resolution'] = 2048
            flag_modified(footage, 'meta')
        db.session.commit()
        db.session.close()

@pytest.mark.access
def test_access(api):

    # Попытка загрузить панораму без авторизации
    # Параметр: стандартная панорама 1536. Без авторизации
    # Ожидаемый результат: 403
    resp = api.put(f'/tours/1/virtual/loading/skyboxes')
    assert resp.status_code == 403

    # Пытаемся загрузить скайбокс без авторизации
    # Параметры: стандартная и бинокулярная панорама 1536
    # ожидаемый результат: 403
    resp = api.put(f'/tours/1/virtual/loading/skyboxes/1')
    assert resp.status_code == 403

    # Отправить тур на сборку без авторизации
    # Ожидаемый результат: 403
    resp = api.post(f'/tours/1/virtual/loading/build')
    assert resp.status_code == 403


def test_put_skyboxes_default_res(api):
    """
    PUT /tours/<id>/loading/skyboxes
    Загрузить панорамы. ID скайбоксов вычисляются из имени файла.
    Input
        {
            'upload_token': TOKEN
            'binocular': bool
        }
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['put_skyboxes']:
            params = {'auth_as': user['email'], 'body': dataset['body']}
            if dataset['id'] == 1:
                set_flow({'TOKEN': ['src/panorama1536.png']})
                # Описание: Попытка загрузить панораму с авторизацией
                # Параметр: Загружена стандартная панорама с разрешением 1536
                # Ожидаемый результат: Добавить панораму может любой, кроме забаненного юзера
                resp = api.put(f'/tours/{tour_id}/virtual/loading/skyboxes', **params)
                if not user['banned'] and user_id in PLAN_IDS.keys():
                    assert resp.status_code == 200
                else:
                    assert resp.status_code in (403, 400)

            if dataset['id'] == 2:
                # Описание: Попытка загрузить панораму с авторизацией
                # Параметр: Загружена стандартная бинокулярная панорама с разрешением 1536
                # Ожидаемый результат: Добавить панораму может любой авторизованный юзер, кроме забаненного
                set_flow({'TOKEN': ['src/panorama_bin_1536.png']})
                resp = api.put(f'/tours/{tour_id}/virtual/loading/skyboxes', **params)
                if not user['banned'] and user_id in PLAN_IDS.keys():
                    assert resp.status_code == 200
                else:
                    assert resp.status_code in (403, 400)


def test_put_skyboxes_max_res(api):
    """
    PUT /tours/<id>/loading/skyboxes
    Загружаем панорамы. В мете тура max_resolution=2048
    Input
        {
            'upload_token': TOKEN
            'binocular': bool
        }
    :param api:
    :param:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = int(user_id) + 10
        for dataset in datasets['put_skyboxes']:
            params = {'auth_as': user['email'], 'body': dataset['body']}

            if dataset['id'] == 1:
                # Описание: Пробуем добавить панораму, разрешение которой не равно дефолтному - 1536
                # Параметры: У съемок добавлен параметр max_resolution=2048
                # ожидаемый результат: Добавить панораму c расширением равным max_resolution из footage.meta
                # может только юзер, у которого plan_id >=30, в остальных случаях панорамы с расширением не равному
                # дефолтному пропускаются.
                set_flow({'TOKEN': ['src/panorama2048.png']})
                resp = api.put(f'/tours/{tour_id}/virtual/loading/skyboxes', **params)

                if user_id in PLAN_IDS and PLAN_IDS[user_id] >= 30:
                    assert resp.status_code == 200
                    assert not resp.warnings
                elif not user['banned'] and user_id in PLAN_IDS.keys():
                    assert resp.status_code == 200
                    assert resp.has_warning('Select the plan that meets your requirements.')
                else:
                    assert resp.status_code in (400, 403)
            if dataset['id'] == 2:
                # Описание: Добавляем бинокулярную панораму с разрешением равному max_resolution из footage.meta
                # Ожидаемый результат: Добавить панораму c расширением равным max_resolution из footage.meta
                # может только юзер, у которого plan_id >=30, в остальных случаях панорамы с расширением не равному
                # дефолтному пропускаются.
                set_flow({'TOKEN': ['src/panorama_bin_2048.png']})
                resp = api.put(f'/tours/{tour_id}/virtual/loading/skyboxes', **params)

                if user_id in PLAN_IDS and PLAN_IDS[user_id] >= 30:
                    assert resp.status_code == 200
                    assert not resp.warnings
                elif not user['banned'] and user_id in PLAN_IDS.keys():
                    assert resp.status_code == 200
                    assert resp.has_warning('Select the plan that meets your requirements.')
                else:
                    assert resp.status_code in (400, 403)


def test_put_skybox(api):
    """
    Сохранить одну панораму
    PUT /tours/<tour_id>/virtual/loading/skyboxes/<skybox_id>
    {
        'pos': vector3,
        'q': quaternion,
        'file_name@flow': 'TOKEN/filename',  // Поместите сюда null, чтобы удалить файл панорамы
        'lr_file_name@flow': 'TOKEN/filename'  // null тут удалит бинокулярную панорамы

    }
    :param api:
    :return:
    """

    for user_id, user in USERS.items():
        tour_id = user_id
        skybox_id = user_id
        for dataset in datasets['put_skybox']:
            params = {'auth_as': user['email'], 'body': dataset['body']}

            if dataset['id'] == 1:
                # Описание: Пытаемся загрузить скайбокс с авторизацией
                # Параметры: стандартная и бинокулярная панорама 1536
                # Ожидаемый результат: Добавить панораму может любой авторизованный юзер, кроме забаненного
                set_flow({'TOKEN': ['src/panorama1536.png', 'src/panorama_bin_1536.png']})
                resp = api.put(f'/tours/{tour_id}/virtual/loading/skyboxes/{skybox_id}', **params)
                if not user['banned'] and user_id in PLAN_IDS.keys():
                    assert resp.status_code == 200
                else:
                    assert resp.status_code in (403, 400)

            if dataset['id'] == 2:
                # Описание: Панорама не имеет числа в имени файла
                # Ожидаемый результат: 200 В этом случае указывается номер скайбокса явно, поэтому требование, чтобы
                # был номер скайбокса в имени файла не нужно
                set_flow({'TOKEN': ['src/panorama.png', 'src/panorama_binocular.png']})
                resp = api.put(f'/tours/{tour_id}/virtual/loading/skyboxes/{skybox_id}', **params)
                if not user['banned'] and user_id in PLAN_IDS.keys():
                    assert resp.status_code == 200
                else:
                    assert resp.status_code in (403, 400)


def test_put_skybox_max_res(api):
    """
    Сохранить панораму
    PUT /tours/<tour_id>/virtual/loading/skyboxes/<skybox_id>

    {
        'pos': vector3,
        'q': quaternion,
        'file_name@flow': 'TOKEN/filename',  // Поместите сюда null, чтобы удалить файл панорамы
        'lr_file_name@flow': 'TOKEN/filename'  // null тут удалит бинокулярную панорамы
    }
    :param api:
    :return:
    """

    for user_id, user in USERS.items():
        tour_id = user_id + 10
        skybox_id = user_id
        for dataset in datasets['put_skybox']:
            params = {'auth_as': user['email'], 'body': dataset['body']}

            if dataset['id'] == 3:
                # Описание: Попытка добавить скайбокс У которого разрешение панорам равно 2048
                # Параметры: У туров есть в мете параметр "max_resolution": 2048,
                # Ожидаемый результат: Добавить панораму c расширением равным max_resolution из footage.meta
                # может только юзер, у которого plan_id >=30, в остальных случаях панорамы с расширением не равному
                # дефолтному пропускаются.
                set_flow({'TOKEN': ['src/panorama2048.png', 'src/panorama_bin_2048.png']})
                resp = api.put(f'/tours/{tour_id}/virtual/loading/skyboxes/{skybox_id}', **params)
                if user_id in PLAN_IDS and PLAN_IDS[user_id] >= 30:
                    assert resp.status_code == 200
                else:
                    assert resp.status_code in (400, 403)

def test_delete_skybox(api):
    """
    DELETE /tours/<int:tour_id>/virtual/loading/skyboxes/<skybox_id>
    Удалить скайбокс.
    :param api:
    :return:
    """
    for user_id, user in USERS.items():

        tour_id = user_id
        skybox_id = '1536'
        # Описание: Попытка удалить скайбокс из загрузки
        # Ожидаемый результат: Удалить панораму может любой, кроме banned
        resp = api.delete(f'/tours/{tour_id}/virtual/loading/skyboxes/{skybox_id}', auth_as=user['email'])
        if not user['banned'] and user_id in PLAN_IDS.keys():
            assert resp.status_code == 204
        else:
            assert resp.status_code in (400, 403)


def test_put_model(api):
    """
    PUT /tours/<tour_id>/virtual/loading/model
    {
        'model@flow': 'TOKEN/filename'
    }
    :param api: 
    :return: 
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['put_model']:
            params = {'auth_as': user['email'], 'body': dataset['body']}

            if dataset['id'] == 1:
                # Попытка добавить модель model-0.obj
                # Ожидаемый результат: добавить может любой, кроме banned
                set_flow({'TOKEN': ['src/model-0.obj']})
                resp = api.put(f'/tours/{tour_id}/virtual/loading/model', **params)
                if not user['banned'] and user_id in PLAN_IDS.keys():
                    assert resp.status_code == 200
                else:
                    assert resp.status_code in (400, 403)


def test_del_model(api):
    """
    Удаляем модель
    DELETE /tours/<tour_id>/virtual/loading/model
    :param api:
    :return:
    """
    for user_id, user in USERS.items():

        tour_id = user_id
        # Описание: Попытка удалить модель
        # Ожидаемый результат: удалить может любой, кроме banned
        resp = api.delete(f'/tours/{tour_id}/virtual/loading/model', auth_as=user['email'], )
        if not user['banned'] and user_id in PLAN_IDS.keys():
            assert resp.status_code == 204
        else:
            assert resp.status_code in (400, 403)

@pytest.mark.bad_requests
def test_exception(api):
    """
    Плохие запросы
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['put_skyboxes']:
            params = {'auth_as': user['email'], 'body': dataset['body']}

            if dataset['id'] == 1:
                # Описание: Попытка добавить скайбоксы в съемку.
                # Параметры: Панорама не имеет номера скайбокса в имени файла
                # Ожидаемый результат: пропускаются панорамы, у которых нет чисел в имени файла
                set_flow({'TOKEN': ['src/panorama.png']})
                resp = api.put(f'/tours/{tour_id}/virtual/loading/skyboxes', **params)
                if not user['banned'] and user_id in PLAN_IDS.keys():
                    assert resp.status_code == 200
                    assert resp.has_warning('Unable to recognize filename')
                elif not user['banned'] and user_id not in PLAN_IDS.keys():
                    assert resp.has_error('You have no access to Virtoaster.')
                    assert resp.status_code == 400
                else:
                    assert resp.status_code == 403



                # Описание: Попытка добавить скайбоксы в съемку.
                # Параметры: Расширение панорамы не равно 1546x9216
                # Ожидаемый результат: такие панорамы пропускаются
                set_flow({'TOKEN': ['src/panorama1024.png']})
                resp = api.put(f'/tours/{tour_id}/virtual/loading/skyboxes', **params)
                if not user['banned'] and user_id in PLAN_IDS.keys():
                    assert resp.status_code == 200
                    assert resp.has_warning('Unsupported resolution in file')
                else:
                    assert resp.status_code in (400, 403)

        # Попытка добавить модель
        # Параметр: У файла расширение не 'obj'
        # Ожидаемый результат: 400
        set_flow({'TOKEN': ['src/tours.json']})
        resp = api.put(f'/tours/{tour_id}/virtual/loading/model',
                       body=datasets['bad_requests']['bad_model']['body'], auth_as=user['email'], )
        if not user['banned'] and user_id in PLAN_IDS.keys():
            assert resp.status_code == 400
            assert resp.has_error('Unsupported 3d model extension.')
        else:
            assert resp.status_code in (400, 403)

        # Описание: Попытка добавить скайбокс
        # Параметры: Расширение панорамы не равно 1546x9216
        # Ожидаемый результат: такие панорамы пропускаются
        set_flow({'TOKEN': ['src/panorama2048.png', 'src/panorama_bin_2048.png']})
        resp = api.put(f'/tours/{tour_id}/virtual/loading/skyboxes/100',
                       auth_as=user['email'], body=datasets['bad_requests']['max_res']['body'], )
        if not user['banned'] and user_id in PLAN_IDS.keys():
            assert resp.status_code == 400
            assert resp.has_error('Unsupported resolution in file')
        else:
            assert resp.status_code in (400, 403)


def test_build_tour(api):
    """
    Отправить тур на сборку
    POST /tours/<int:tour_id>/virtual/loading/build
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = user_id

        # Описание: пытаемся отправить тур на сборку
        # Параметры: с токеном авторизации
        # Ожидаемый результат: Отправить тур на сборку может любой юзер, кроме забаненного
        resp = api.post(f'/tours/{tour_id}/virtual/loading/build', auth_as=user['email'])
        if not user['banned'] and user_id in PLAN_IDS.keys():
            assert resp.status_code == 200
            assert 'bgjobs' in resp.object

        else:
            assert resp.status_code in (400, 403)
