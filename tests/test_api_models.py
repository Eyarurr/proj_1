import os

import json
import datetime

from tests.common import set_flow
from visual import create_app
from visual.core import db
from visual.models import User, Tour, Footage, AuthToken
from sqlalchemy.orm.attributes import flag_modified

from visual.models.meta import FootageMetaInside
from visual.util import unzip_footage_tour
from .conftest import SRC_DIR

with open(os.path.join(SRC_DIR, 'meta.json')) as fm:
    meta = json.load(fm)

SKYBOX_REMOVAL = '14'

datasets = {
    'add_model': [
        {'id': 1, 'query_string': {},
         'body': {'model@flow': 'TOKEN/model-0.obj'}},
        {'id': 2, 'query_string': {'filename': 'new_name_1.obj', 'calc_passways': 1},
         'body': {'model@flow': 'TOKEN/model-0.obj'}},
        {'id': 3, 'query_string': {'filename': 'new_name_2.obj', 'calc_passways': 0},
         'body': {'model@flow': 'TOKEN/model-0.obj'}},
    ], 'add_model_broken_data': [
        {'id': 1, 'query_string': {},
         'body': {}},
        {'id': 2, 'query_string': {'filename': 'new_name_1.obj', 'calc_passways': 1},
         'body': {'model@flow': 'TOKEN/model-0.obj'}},

    ],
    'calc_passways': [
        {'id': 1, 'query_string': {'overwrite': 0, 'background': 0}},
        {'id': 2, 'query_string': {'overwrite': 0, 'background': 1}},
        {'id': 3, 'query_string': {'overwrite': 1, 'background': 0}},
        {'id': 4, 'query_string': {'overwrite': 1, 'background': 1}},
    ]}

USERS = {}
TOURS = {}
FOOTAGES = {}


def setup_module():
    """
    Создаем обычного юзера.
    Добавим шесть туров и шесть съемок. В каждую съемку распакуем файлы ассетов из 14 скайбоксов, добавим модель и мету.
    У нечетных туров удаляем четырнадцатый скайбокс. У четных - удаляем из меты ключ passways
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        users = [
            {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com'},
        ]
        for kwargs in users:
            user = User(email_confirmed=True, **kwargs)
            user.auth_tokens.append(
                AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30),
                          ip='0.0.0.0'))
            db.session.add(user)

            for i in range(6):
                tour = Tour(user_id=user.id, title='tour',
                            footage=Footage(user_id=user.id, _status='testing', type='real', meta=meta))
                db.session.add(tour)
                db.session.flush()
                tour.mkdir()
                tour.footage.mkdir()
                path = os.path.join(SRC_DIR, 'tours', 'tour-20335.zip')
                unzip_footage_tour(path, footage=tour.footage, tour=tour)
                if tour.id % 2 == 0:
                    del tour.footage.meta['passways']
                else:
                    meta_ = FootageMetaInside(tour.footage)
                    meta_.skybox_delete(SKYBOX_REMOVAL)
                    del tour.footage.meta['skyboxes'][SKYBOX_REMOVAL]

                USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
                TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title', 'meta')}
                FOOTAGES[tour.id] = {k: getattr(tour.footage, k) for k in ('id', 'user_id', 'meta')}
                FOOTAGES[tour.id]['in_files'] = tour.footage.in_files()

            flag_modified(tour.footage, 'meta')
        db.session.commit()
        db.session.close()


def test_recalc_passways(api):
    """
    Пересчитывает графа достижимости (
    POST /footages/<int:footage_id>/passways/calc
    query string
    overwrite - перезаписывать passways в мете или нет : 1 перезаписывать 0 -нет
    {
    passways: [[s1, s2], [s1, s3], ...]
    }
    background - пересчитывать в фоне или нет: 1 в фоне  0 - нет
    {'bgjobs': ' ', 'result': {}}
    """
    for dataset in datasets['calc_passways']:
        if dataset['id'] == 1:
            for footage_id in (1, 2):
                # Пытаемся посчитать passways не в ФОНЕ, не перезаписывая мету. Без авторизации
                #  Ожидаемый результат: 403
                resp = api.post(f'/footages/{footage_id}/passways/calc', query_string=dataset['query_string'])
                assert resp.status_code == 403

                # Пытаемся посчитать passways не перезаписывая мету
                # Параметры {'overwrite': 0, 'background': 0}}. Тестируем на двух съемках: 
                # Ожидаемый результат: Авторизированный юзер может посчитать passways.
                resp = api.post(f'/footages/{footage_id}/passways/calc',
                                auth_as='anna@biganto.com', query_string=dataset['query_string'])

                assert resp.status_code == 200
                assert 'result' in resp.object
                assert 'passways' in resp.object['result']
                if footage_id == 1:
                    # У съемки нет SKYBOX_REMOVAL, но есть passways и SKYBOX_REMOVAL in passways
                    # Ожидаемый результат: у съемки нет SKYBOX_REMOVAL, но есть passways и SKYBOX_REMOVAL in passways
                    assert 'passways' in resp.result  # возвращается посчитанный passways
                    assert SKYBOX_REMOVAL not in set(sum(resp.result['passways'], []))
                elif footage_id == 2:
                    # У съемки не удален SKYBOX_REMOVAL, но не посчитан passways
                    # Ожидаемый результат: у съемки есть SKYBOX_REMOVAL, но нет passways
                    assert 'passways' in resp.result
                    assert SKYBOX_REMOVAL in set(sum(resp.result['passways'], []))  # не перезаписывается мета
        """"""
        if dataset['id'] == 2:
            for footage_id in (1, 2):
                # Попытка пересчитать passways в фоне не перезаписывая результат.
                # Параметры: {'overwrite': 0, 'background': 1}
                # Ожидаемый результат: Авторизированный юзер может посчитать passways.
                resp = api.post(f'/footages/{footage_id}/passways/calc',
                                auth_as='anna@biganto.com', query_string=dataset['query_string'])

                if footage_id == 1:
                    # У съемки нет SKYBOX_REMOVAL, но есть passways и SKYBOX_REMOVAL in passways
                    # Ожидаемый результат:  204
                    assert resp.status_code == 204
                elif footage_id == 2:
                    # У съемки не удален SKYBOX_REMOVAL, но не посчитан passways
                    # Ожидаемый результат: вернется id задачи на пересчет passways в фоне
                    assert 'passways' not in FOOTAGES[footage_id]['meta']
                    assert 'bgjobs' in resp.object
        """"""
        if dataset['id'] == 3:
            footage_id = 3
            # Попытка ПЕНРЕЗАПИСАТЬ passways не в фоне
            # query_string': {'overwrite': 1, 'background': 0}},
            # Ожидаемый результат: Авторизированный юзер может посчитать passways.

            # У съемки удален SKYBOX_REMOVAL, есть passways и SKYBOX_REMOVAL in passways
            # Ожидаемый результат: 200 вернется рассчитанный passways.
            resp = api.post(f'/footages/{footage_id}/passways/calc',
                            auth_as='anna@biganto.com', query_string=dataset['query_string'])
            assert resp.status_code == 200
            assert SKYBOX_REMOVAL not in set(sum(resp.result['passways'], []))

            footage_id = 4
            # У съемки не удален SKYBOX_REMOVAL, и не посчитан passways
            # Ожидаемый результат: 200 вернется рассчитанный passways.
            resp = api.post(f'/footages/{footage_id}/passways/calc',
                            auth_as='anna@biganto.com', query_string=dataset['query_string'])
            assert resp.status_code == 200
            assert resp.result['passways']
            assert SKYBOX_REMOVAL in set(sum(resp.result['passways'], []))
        """"""
        if dataset['id'] == 4:
            for footage_id in (5, 6):
                # Попытка ПЕРЕЗАПИСАТЬ passways в фоне
                # Параметры: {'overwrite': 1, 'background': 1}},
                # Ожидаемый результат: Для обоих случаев отправляется в очередь задача на пересчет passways
                resp = api.post(f'/footages/{footage_id}/passways/calc', auth_as='anna@biganto.com',
                                query_string=dataset['query_string'])
                assert resp.status_code == 200
                assert 'bgjobs' in resp.object


def test_add_model(api):
    """
    Залить модель
    PUT /footages/<id>/model
    query string:
    filename — имя файла для новой модели. Если параметр не указан или пуст, то модель будет называться
    по-умолчанию ("model-0.obj")
    calc_passways=1|0 — считать ли граф достижимости. Default=1
    {
    "model@flow": "TOKEN/filename"
    }
    :param api:
    :return:
    """
    for dataset in datasets['add_model']:
        set_flow({'TOKEN': ['src/model-0.obj']})
        # Попытка загрузить новую модель без авторизации
        # Ожидаемый результат: 403
        footage_id = 1
        resp = api.put(f'/footages/{footage_id}/model', query_string=dataset['query_string'], body=dataset['body'])
        assert resp.status_code == 403

        # Попытка загрузить новую модель с авторизацией
        # Ожидаемый результат: авторизированный юзер может загрузить новую модель
        # Доказательство: 200 и существование нового файла в асетах
        resp = api.put(f'/footages/{footage_id}/model', auth_as='anna@biganto.com',
                       query_string=dataset['query_string'],
                       body=dataset['body'])
        assert resp.status_code == 200
        if dataset['query_string'].get('filename', None):
            new_file = os.path.join(FOOTAGES[footage_id]['in_files'], 'models', dataset['query_string']['filename'])
            assert os.path.exists(new_file)
        else:
            assert os.path.exists(os.path.join(FOOTAGES[footage_id]['in_files'], 'models', 'model-0.obj'))


def test_add_model_broken(api):
    """
    Плохие запросы
    """
    for dataset in datasets['add_model_broken_data']:
        # Попытка загрузить новую модель с авторизацией. Нет model@flow в теле
        # Ожидаемый результат: 400
        if dataset['id'] == 1:
            resp = api.put(f'/footages/1/model', auth_as='anna@biganto.com', query_string=dataset['query_string'],
                           body=dataset['body'])

            assert resp.status_code == 400
            resp.has_error('Malformed')
        # Попытка загрузить новую модель с авторизацией. Нет файла в TOKEN
        # Ожидаемый результат: 400
        if dataset['id'] == 2:
            resp = api.put(f'/footages/1/model', auth_as='anna@biganto.com', query_string=dataset['query_string'],
                           body=dataset['body'])

            assert resp.status_code == 400
            resp.has_error('Source file TOKEN/model-0.obj not found')


def test_model_size_calc(api):
    """
    Вычисление размеров модели
    POST /footages/<footage_id>/model_size/calc
    :param api:
    :return:
    """
    # Попытка вычислить размер модели без авторизации
    # Ожидаемый результат: 403
    resp = api.post(f'/footages/1/model_size/calc')
    assert resp.status_code == 403

    #  Попытка вычислить размер модели с авторизации
    # Ожидаемый результат: авторизированный юзер может вычислить размер модели
    resp = api.post(f'/footages/1/model_size/calc', auth_as='anna@biganto.com')
    assert resp.status_code == 200
