import copy
import datetime
import datauri
import pytest

from tests.common import set_flow
from visual import create_app
from visual.core import db
from visual.models import User, Footage, Tour, TeamMember, AuthToken

datasets = {
    'post_navigator': [
        {"id": 1, 'title': 'navigator',
         'body': {'img': '/srv/biganto.com/var/flow-upload/TOKEN/256x256.jpg', 'img@resize': [200, 200], 'skybox': '1',
                  'q': [1, 2, 3, 4], 'title': 'имя навигатора',
                  }},
        {"id": 2, 'title': 'navigator',
         'body': {'img@flow': 'TOKEN/panorama.png', 'img@resize': [256, 256], 'skybox': '1', 'q': [1, 2, 3, 4],
                  'title': 'имя навигатора',
                  }},
        {"id": 3, 'title': 'navigator',
         'body': {'img@dataurl': datauri.DataURI.from_file('/srv/biganto.com/tests/src/1-1.jpg'),
                  'img@resize': [200, 200], 'skybox': '1', 'q': [1, 2, 3, 4], 'title': 'имя навигатора',
                  }}],
    'put_navigator_all': [
        {"id": 1, 'title': 'navigator',
         'body': [
             {'img': '/srv/biganto.com/var/flow-upload/TOKEN/panorama.png', 'img@resize': [200, 200], 'skybox': '1',
              'q': [1, 2, 3, 4], 'title': 'put_navigator_all'
              },
             {'img@flow': 'TOKEN/256x256.jpg', 'img@resize': [256, 256], 'skybox': '1', 'q': [1, 2, 3, 4],
              'title': 'put_navigator_all'
              },
             {'img@dataurl': datauri.DataURI.from_file('/srv/biganto.com/tests/src/256x256.jpg'),
              'img@resize': [200, 200], 'skybox': '1', 'q': [1, 2, 3, 4], 'title': 'put_navigator_all'
              },
         ]}],
}
USERS = {}
TOURS = {}


def setup_module():
    """
    Создаем 5 юзеров. Юзеры с id 1, 2, 3 - нормальные, 2 - с ролью 'tours'. 4 - забаненный, 5 - помечен как удаленный
    Всем, кроме 6 добавляем подписку virtoaster-trial
    У каждого юзера по одному туру и съемке (_status='testing', type='real').
    В var/flow-upload/TOKEN копируем три файла 'src/1-1.jpg', 'src/256x256.jpg', 'src/panorama.png'
    :return:
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
        set_flow({'TOKEN': ['src/1-1.jpg', 'src/256x256.jpg', 'src/panorama.png']})


@pytest.mark.access
def test_access_skybox(api):
    for user_id, user in USERS.items():
        tour_id = user_id

        #  Попытка добавить навигатор. Без авторизации
        #  Ожидаемый результат: 403
        resp = api.post(f'/tours/{tour_id}/virtual/navigator')
        assert resp.status_code == 403

        #  Попытка изменить навигатор без авторизации
        #  Ожидаемый результат: 403
        resp = api.put(f'/tours/{tour_id}/virtual/navigator/1')
        assert resp.status_code == 403

        #  Пытаемся ИЗМЕНИТЬ навигатор полностью без авторизации
        #  Ожидаемый результат: 403
        resp = api.put(f'/tours/{tour_id}/virtual/navigator')
        assert resp.status_code == 403


def test_post_navigator(api):
    """
    Добавить навигатор
    POST /tours/<tour_id>/virtual/navigator
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['post_navigator']:

            #  Попытка добавить навигатор. С авторизацией
            #  Ожидаемый результат: Добавить СЕБЕ навигатор может любой авторизированный юзер, кроме забаненного
            resp = api.post(f'/tours/{tour_id}/virtual/navigator', auth_as=user['email'], body=dataset['body'])
            if not user['banned']:
                assert resp.status_code == 200
            else:
                assert resp.status_code == 403


def test_get_navigator(api):
    """
    Получаем список всех навигаторов
    GET /tours/<tour_id>/virtual/navigator
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        #  Попытка получить навигатор без авторизации
        #  Ожидаемый результат: можно получить список всех навигаторов у всех юзеров кроме забаненного, удаленного и
        # юзера без подписки 'virtoaster'
        resp = api.get(f'/tours/{tour_id}/virtual/navigator')
        if user_id not in (4, 5, 6):
            assert resp.status_code == 200
        else:
            assert resp.status_code == 403

        #  Попытка получить список своих навигаторов
        #  Ожидаемый результат: Любой юзер, кроме забаненного можно получить список своих навигаторов
        resp = api.get(f'/tours/{tour_id}/virtual/navigator', auth_as=user['email'])
        if not user['banned']:
            assert resp.status_code == 200
        else:
            assert resp.status_code == 403


def test_put_navigator(api):
    """
    Изменить один элемент навигатора
    PUT /tours/<tour_id>/virtual/navigator/<index>
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['post_navigator']:
            
            #  Пытаемся ИЗМЕНИТЬ свой навигатор
            #  Ожидаемый результат: Изменить навигатор может любой юзер, кроме забаненного
            dataset['body']['title'] = 'PUT_' + 'new title'
            resp = api.put(f'/tours/{tour_id}/virtual/navigator/{dataset["id"] - 1}', auth_as=user['email'], body=dataset['body'])
            if not user['banned']:
                assert resp.status_code == 200, resp.errors
            else:
                assert resp.status_code == 403

            #  Пытаемся ДОБАВИТЬ навигатор
            #  Ожидаемый результат: 404. Забаненный юзер не может добавлять навигатор - 403
            dataset['body']['title'] = 'PUT_' + 'new title'
            resp = api.put(f'/tours/{tour_id}/virtual/navigator/10', auth_as=user['email'], body=dataset['body'])
            if not user['banned']:
                assert resp.status_code == 404
                assert resp.has_error('Navigator item not found.')
            else:
                assert resp.status_code == 403


def test_put_navigator_all(api):
    """
    Изменить весь навигатор
    PUT /tours/<tour_id>/virtual/navigator
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['put_navigator_all']:

            #  Авторизированный юзер пытается ИЗМЕНИТЬ весь свой навигатор полностью
            #  Ожидаемый результат: Изменить навигатор может любой юзер, кроме забаненного
            resp = api.put(f'/tours/{tour_id}/virtual/navigator', auth_as=user['email'], body=dataset['body'])
            if not user['banned']:
                assert resp.status_code == 200
            else:
                assert resp.status_code == 403


def test_delete_navigator(api):
    """
    Тестируем удаление всех навигаторов в туре
    DELETE /tours/<tour_id>/virtual/navigator
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        #  Попытка удалить все навигаторы без авторизации
        #  Ожидаемый результат: запрещено удаление без авторизации 403
        resp = api.delete(f'/tours/{tour_id}/virtual/navigator')
        assert resp.status_code == 403

        #  Попытка удалить все навигаторы с авторизацией
        #  Ожидаемый результат: удалить все свои навигаторы может любой авторизированный юзер, кроме забаненного
        # todo: Необычный status_code - 200, при удалении часто возвращается 204
        resp = api.delete(f'/tours/{tour_id}/virtual/navigator', auth_as=user['email'])
        if not user['banned']:
            assert resp.status_code == 200
        else:
            assert resp.status_code == 403


@pytest.mark.bad_requests
def test_exception(api):
    """
    Плохие запросы
    :param api:
    :return:
    """
    dataset_copy = copy.deepcopy(datasets['post_navigator'])
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in dataset_copy:
            set_flow({'TOKEN': ['src/1-1.jpg', 'src/256x256.jpg', 'src/panorama.png']})
            #  Неизвестное свойство
            #  Ожидаемый результат: 200, свойство не добавляется
            dataset['body']['bad_props'] = 'BAD_POPS'
            resp = api.post(f'/tours/{tour_id}/virtual/navigator', auth_as=user['email'], body=dataset['body'])
            if not user['banned']:
                assert resp.status_code == 200
                resp.has_warning('Unknown input property bad_props')
            else:
                assert resp.status_code == 403
            del dataset['body']['bad_props']

            #  Отсутствует свойство skybox
            #  Ожидаемый результат: 400
            del dataset['body']['skybox']
            resp = api.post(f'/tours/{tour_id}/virtual/navigator', auth_as=user['email'], body=dataset['body'])
            if not user['banned']:
                assert resp.status_code == 400
                resp.has_error('No skybox specified when creating navigator element.')
            else:
                assert resp.status_code == 403
            dataset['body']['skybox'] = 1

