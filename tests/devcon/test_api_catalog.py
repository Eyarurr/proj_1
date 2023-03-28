"""
Тесты методов API Умной Стройки: проекты и членство.

Сценарий:
setup_module() создаёт юзеров
    1. owner@biganto.com. Будущая хозяйка проекта
    2. admin@biganto.com. Будущий админ проекта.
    3. cameraman@biganto.com. Будущий съёмщик.
    4. plotman@biganto.com. Будущий чертёжник.
    5. viewer@biganto.com. Будущий просто хуй с горы.
    6. cocksucker@biganto.com. Юзер, не участвующий в проекте.

    Каждому даёт по авторизационному токену, равному User.email.

    Туры:
    1. Tour 1 (cameraman)
    2. Tour 2 (cameraman)
    3. Tour 3 (admin)

test_post_projects() создаёт 3 проекта:
    "Ниф-Ниф" (owner=anna)
    "Нуф-Нуф" (owner=anna)
    "Наф-Наф" (owner=annd)
    "Лубянка" (owner=cocksucker)

test_post_members() приглашает юзеров в проекты:
    "Ниф-Ниф": anna (owner), admin, cameraman, plotman, viewer
    "Нуф-Нуф": anna (owner), admin, viewer
    "Наф-Наф": anna (owner), cameraman
    "Лубянка": cocksucker (owner)

test_put_projects() переименовывает Лубянку в Музей седых мудей и заливает разными способами картинки

test_put_member() в Ниф-Нифе админом камерамэну роли на камерамена и плотмена

test_post_areas() создаёт в Ниф-Нифе области:
    Подъезд 1     (MEMO['a-p1'])
        Этаж 1    (MEMO['a-p1-e1'])
        Этаж 2    (MEMO['a-p1-e2'])
    Подъезд 2     (MEMO['a-p2'])
        Этаж 1    (MEMO['a-p2-e1'])
        Этажъ 2   (MEMO['a-p2-e2'])  // Будет исправлен на "Этаж 2" в test_put_area

test_post_tours() добавляет туры в области проекта Ниф-Ниф:
    Подъезд 1     (MEMO['a-p1'])      Tour 1
        Этаж 1    (MEMO['a-p1-e1'])   Tour 2  // перенесётся в p1-e2 в test_put_tours
        Этаж 2    (MEMO['a-p1-e2'])   Tour 3
    Подъезд 2     (MEMO['a-p2'])
        Этаж 1    (MEMO['a-p2-e1'])   Tour1, Tour2, Tour3
        Этаж 2    (MEMO['a-p2-e2'])

test_put_tours():
    Подъезд 1     (MEMO['a-p1'])      Tour 1
        Этаж 1    (MEMO['a-p1-e1'])
        Этаж 2    (MEMO['a-p1-e2'])   Tour 2, Tour 3
    Подъезд 2     (MEMO['a-p2'])
        Этаж 1    (MEMO['a-p2-e1'])   Tour1, Tour2, Tour3
        Этаж 2    (MEMO['a-p2-e2'])
"""
import pytest
import os
import datauri

from visual import create_app
from visual.core import db
from visual.models import Footage, Tour
from ..common import set_flow
from .setup import create_users, create_tours

# Сторадж для передачи данных между тестами
MEMO = {
    'users': {},
    'drawings': {}
}


def setup_module():
    """
    Создаёт стандартных юзеров через create_users()
    Создаёт туры:
    1. Tour 1 (cameraman)
    2. Tour 2 (cameraman)
    3. Tour 3 (admin)
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()

        MEMO['users'] = create_users()
        create_tours()

        db.session.commit()


def find_user(email):
    """Ищет в словаре словаре юзеров MEMO['user'] юзера по емейлу"""
    for user in MEMO['users'].values():
        if user['email'] == email:
            return user
    return None


@pytest.mark.bad_requests
def test_post_projects_bad_requests(api):
    """
    POST /devcon/projects.

    В итоге создаёт четыре проекта:
    "Ниф-Ниф": anna (owner)
    "Нуф-Нуф": anna (owner)
    "Наф-Наф": anna (owner)
    "Лубянка": cocksucker (owner)
    :param api:
    :return:
    """
    # Отсутствует title
    resp = api.post('/devcon/projects', {}, auth_as='owner@biganto.com')
    assert resp.status_code == 400

    # title неверного типа
    resp = api.post('/devcon/projects', {'title': False}, auth_as='owner@biganto.com')
    assert resp.status_code == 400

    # Пустой title
    resp = api.post('/devcon/projects', {'title': ''}, auth_as='owner@biganto.com')
    assert resp.status_code == 400

    # Пустой title
    resp = api.post('/devcon/projects', {'title': ' '}, auth_as='owner@biganto.com')
    assert resp.status_code == 400

    # details неверного типа
    resp = api.post('/devcon/projects', {'title': 'Домик Ниф-Нифа', 'details': False}, auth_as='owner@biganto.com')
    assert resp.status_code == 400


def test_post_projects(api):
    # Нормальный запрос (4 шт.)
    set_flow({
        'TOKEN': ['src/256x256.jpg']
    })
    bodies = [
        ('owner@biganto.com', 'nifnif_id', {
            'title': 'Домик Ниф-Нифа',
            'details': {'address': 'ул. Строителей, д. 25'},
            'icon': 'flow@TOKEN/256x256.jpg'
        }),
        ('owner@biganto.com', 'nufnuf_id', {'title': 'Домик Нуф-Нуфа'}),
        ('owner@biganto.com', 'nafnaf_id', {'title': 'Домик Наф-Нафа'}),
        ('cocksucker@biganto.com', 'lubyanka_id', {'title': 'Лубянка'}),
    ]
    for auth_as, memo_key, body in bodies:
        resp = api.post('/devcon/projects', body, auth_as=auth_as)
        assert resp.status_code == 200
        assert resp.result
        assert resp.result['title'] == body['title']
        if 'details' in body:
            assert resp.result['details'] == body['details']
        if 'icon' in body:
            assert resp.result['icon'] is not None

        user = MEMO['users'][resp.result['user']['id']]
        assert resp.result['user']['name'] == user['name']

        assert 'super' in resp.result['membership']['roles']
        user = find_user(auth_as)
        assert resp.result['membership']['user']['name'] == user['name']
        MEMO[memo_key] = resp.result['id']


@pytest.mark.bad_requests
def test_post_members_bad_requests(api):
    """
    POST /devcon/projects/<id>/members

    Приглашает юзеров в проекты:
    "Ниф-Ниф": anna (owner), admin, cameraman, plotman, viewer
    "Нуф-Нуф": anna (owner), admin, viewer
    "Наф-Наф": anna (owner), cameraman
    "Лубянка": cocksucker (owner)
    """
    # Кривые тела запросов
    bad_bodies = [
        {}, {'email': ''}, {'email': False}, {'email': 'this is not email address'},
        {'email': 'admin@biganto.com', 'roles': 1},
        {'email': 'admin@biganto.com', 'roles': []},
        {'email': 'admin@biganto.com', 'roles': [1, False, None]},
        {'email': 'admin@biganto.com', 'roles': ['super']},
    ]
    for body in bad_bodies:
        resp = api.post(f'/devcon/projects/{MEMO["nifnif_id"]}/members', body, auth_as='owner@biganto.com')
        assert resp.status_code == 400 or resp.status_code == 403, body

    # @todo: приглашаем пользователя не в свой проект или в несуществующий проект


@pytest.mark.access
def test_post_members_access(api):
    # Приглашаем юзера в проект, где мы не owner и не admin
    body = {'email': 'cocksucker@biganto.com', 'roles': ['viewer']}
    resp = api.post(f'/devcon/projects/{MEMO["nifnif_id"]}/members', body, auth_as='cocksucker@biganto.com')
    assert resp.status_code == 403 or resp.status_code == 404
    resp = api.post(f'/devcon/projects/{MEMO["nifnif_id"]}/members', body, auth_as='viewer@biganto.com')
    assert resp.status_code == 403 or resp.status_code == 404


def test_post_members(api):
    # Нормальные приглашения
    invites = {
        'nifnif_id': [('admin@biganto.com', 'admin'), ('cameraman@biganto.com', 'cameraman'),
                      ('plotman@biganto.com', 'plotman'), ('viewer@biganto.com', 'viewer')],
        'nufnuf_id': [('admin@biganto.com', 'admin'), ('viewer@biganto.com', 'plotman')],
        'nafnaf_id': [('cameraman@biganto.com', 'cameraman')]
    }
    for idkey, members in invites.items():
        for email, role in members:
            resp = api.post(f'/devcon/projects/{MEMO[idkey]}/members', {'email': email, 'roles': [role]}, auth_as='owner@biganto.com')
            assert resp.status_code == 204, f'{idkey} - {role}: {resp.object}'

    # Приглашаем существующего участника проекта
    resp = api.post(f'/devcon/projects/{MEMO["nufnuf_id"]}/members', {'email': 'viewer@biganto.com', 'roles': ['viewer']}, auth_as='owner@biganto.com')
    assert resp.status_code == 204


@pytest.mark.access
def test_put_project_access(api):
    """
    PUT /devcon/projects/<id>
    :param api:
    :return:
    """
    # Лезем править не свой или не существующий проект
    # [(project_id, auth_as), ...]
    attempts = [
        (MEMO['nifnif_id'], 'cocksucker@biganto.com'),  # Не состоит в проекте
        (MEMO['nifnif_id'], 'cameraman@biganto.com'),   # Не админ и не хозяин
        (65535, 'owner@biganto.com'),   # Несуществующий проект
    ]
    for project_id, auth_as in attempts:
        resp = api.put(f'/devcon/projects/{project_id}', {'title': 'Altered', 'details': {'foo': 'bar'}}, auth_as=auth_as)
        assert resp.status_code == 403 or resp.status_code == 404


@pytest.mark.bad_requests
def test_put_project_bad_requests(api):
    # Кривые тела запросов
    attempts = [
        {'title': False},
        {'title': ''},
        {'title': ' '},
        {'details': False},
    ]
    for body in attempts:
        resp = api.put(f'/devcon/projects/{MEMO["lubyanka_id"]}', body, auth_as='cocksucker@biganto.com')
        assert resp.status_code == 400


def test_put_project(api):
    set_flow({
        'TOKEN': ['src/256x256.jpg']
    })
    # Теперь корректный запрос
    body = {
        'title': 'Музей седых мудей',
        'details': {'foo': 'bar'},
        'icon': 'flow@TOKEN/256x256.jpg'
    }
    resp = api.put(f'/devcon/projects/{MEMO["lubyanka_id"]}', body, auth_as='cocksucker@biganto.com')
    assert resp.status_code == 200
    assert resp.result['title'] == body['title']
    assert resp.result['details'] == body['details']
    assert resp.result['icon'] is not None
    prev_icon = resp.result['icon']

    # Корректный запрос, заливаем картинку через base64
    app = create_app('config.test.py')
    with app.app_context():
        path = os.path.join(app.config['FLOW_UPLOAD_TMP_DIR'], 'TOKEN', '256x256.jpg')

    body = {
        'title': 'Музей седых мудей',
        'details': {'foo': 'bar'},
        'icon': 'dataurl@' + datauri.DataURI.from_file(path)
    }
    resp = api.put(f'/devcon/projects/{MEMO["lubyanka_id"]}', body, auth_as='cocksucker@biganto.com')
    assert resp.status_code == 200
    assert resp.result['icon'] is not None
    assert resp.result['icon'] != prev_icon


@pytest.mark.access
def test_put_member_access(api):
    """
    PUT /devcon/projects/<id>/member/<id>
    """
    body = {'roles': ['cameraman', 'plotman']}
    # Запрашиваем участника из проекта, где нас нет (Коксакером лезем в Нуф-Нуфа)
    resp = api.put(f'/devcon/projects/{MEMO["nufnuf_id"]}/members/1', body, auth_as='cocksucker@biganto.com')
    assert resp.status_code == 403 or resp.status_code == 404

    # Запрашиваем несуществующего участника (Вьюера из Наф-Нафа)
    resp = api.put(f'/devcon/projects/{MEMO["nafnaf_id"]}/members/5', body, auth_as='owner@biganto.com')
    assert resp.status_code == 404

    # Запрашиваем изменение участника, где мы не админ (Камерамэном из Наф-Нафа меняем Плотмена)
    resp = api.put(f'/devcon/projects/{MEMO["nifnif_id"]}/members/4', body, auth_as='cameraman@biganto.com')
    assert resp.status_code == 403

    # Просим админом сделать owner'а другому юзеру
    resp = api.put(f'/devcon/projects/{MEMO["nifnif_id"]}/members/3', {'roles': ['super']}, auth_as='cameraman@biganto.com')
    assert resp.status_code == 403


def test_put_member(api):
    # Меняем в Ниф-Нифе админом камерамэну роли на камерамена и плотмена
    body = {'roles': ['cameraman', 'plotman']}
    resp = api.put(f'/devcon/projects/{MEMO["nifnif_id"]}/members/3', body, auth_as='admin@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert set(resp.result['roles']) == set(body['roles'])


@pytest.mark.access
def test_get_members_access(api):
    # Запрашиваем участника из проекта, где нас нет (Коксакером лезем в Нуф-Нуфа)
    resp = api.get(f'/devcon/projects/{MEMO["nufnuf_id"]}/members/1', auth_as='cocksucker@biganto.com')
    assert resp.status_code == 403 or resp.status_code == 404

    # Запрашиваем несуществующего участника (Вьюера из Наф-Нафа)
    resp = api.get(f'/devcon/projects/{MEMO["nafnaf_id"]}/members/5', auth_as='owner@biganto.com')
    assert resp.status_code == 404


def test_get_members(api):
    """
    GET /devcon/projects/<id>/members
    GET /devcon/projects/<id>/members/<id>
    """
    # offset, limit, sort
    resp = api.get(f'/devcon/projects/{MEMO["nifnif_id"]}/members', query_string={'offset': 1, 'limit': 2, 'sort': 'name'}, auth_as='owner@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert len(resp.result) == 2
    assert resp.result[0]['user']['name'] == 'Админ'
    assert resp.result[1]['user']['name'] == 'Визитёр'

    # Получаем одного участника (Админа из Ниф-Нифа)
    resp = api.get(f'/devcon/projects/{MEMO["nifnif_id"]}/members/2', auth_as='cameraman@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert resp.result['user']['name'] == 'Админ'
    assert resp.result['roles'] == ['admin']


@pytest.mark.access
def test_post_areas_access(api):
    # Доступ: не свой проект, недостаточно прав
    access = [
        (65535, 'owner@biganto.com'),  # Несуществующий проект
        (MEMO['nufnuf_id'], 'plotman@biganto.com'),  # Меня нет в проекте
        (MEMO['nafnaf_id'], 'cameraman@biganto.com'),  # Я есть в проекте, но не админ и не оунер
    ]
    for project_id, auth_as in access:
        resp = api.post(f'/devcon/projects/{project_id}/areas', {'title': 'A'}, auth_as=auth_as)
        assert resp.status_code == 403 or resp.status_code == 404, (project_id, auth_as)


@pytest.mark.bad_requests
def test_post_area_bad_requests(api):
    # Плохие тела запроса
    bad_bodies = [
        {},
        {'title': False},
        {'title': ''},
        {'title': '  '},
        {'title': 'Вот нахуя вчера после водки нужно было пить шартрез?', 'parent_id': 555}
    ]
    for body in bad_bodies:
        resp = api.post(f'/devcon/projects/{MEMO["nifnif_id"]}/areas', body, auth_as='admin@biganto.com')
        assert resp.status_code in (400, 404), body


def test_post_areas(api):
    """
    Создаёт в Ниф-Нифе области:
    Подъезд 1     (MEMO['a-p1'])
        Этаж 1    (MEMO['a-p1-e1'])
        Этаж 2    (MEMO['a-p1-e2'])
    Подъезд 2     (MEMO['a-p2'])
        Этаж 1    (MEMO['a-p2-e1'])
        Этажъ 2    (MEMO['a-p2-e2'])  // Будет исправлен на "Этаж 2" в test_put_area
    """
    resp = api.post(f'/devcon/projects/{MEMO["nifnif_id"]}/areas', {'title': 'Подъезд 1'}, auth_as='admin@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert resp.result['parent_id'] is None
    assert resp.result['title'] == 'Подъезд 1'
    assert resp.result['sort'] == 1
    MEMO['a-p1'] = resp.result['id']

    resp = api.post(f'/devcon/projects/{MEMO["nifnif_id"]}/areas', {'title': 'Подъезд 2'}, auth_as='admin@biganto.com')
    assert resp.result['sort'] == 2
    MEMO['a-p2'] = resp.result['id']

    resp = api.post(f'/devcon/projects/{MEMO["nifnif_id"]}/areas', {'title': 'Этаж 1', 'parent_id': MEMO['a-p1']}, auth_as='admin@biganto.com')
    assert resp.result['parent_id'] == MEMO['a-p1']
    assert resp.result['sort'] == 1
    MEMO['a-p1-e1'] = resp.result['id']

    resp = api.post(f'/devcon/projects/{MEMO["nifnif_id"]}/areas', {'title': 'Этаж 2', 'parent_id': MEMO['a-p1']}, auth_as='admin@biganto.com')
    assert resp.result['sort'] == 2
    MEMO['a-p1-e2'] = resp.result['id']

    resp = api.post(f'/devcon/projects/{MEMO["nifnif_id"]}/areas', {'title': 'Этаж 1', 'parent_id': MEMO['a-p2'], 'sort': 100}, auth_as='admin@biganto.com')
    assert resp.status_code == 200
    assert resp.result['sort'] == 100
    MEMO['a-p2-e1'] = resp.result['id']

    resp = api.post(f'/devcon/projects/{MEMO["nifnif_id"]}/areas', {'title': 'Этажъ 2', 'parent_id': MEMO['a-p2']}, auth_as='admin@biganto.com')
    assert resp.status_code == 200
    assert resp.result['sort'] == 101
    MEMO['a-p2-e2'] = resp.result['id']


def test_post_tours(api):
    """
    Добавляет туры в области проекта Ниф-Ниф:
    Подъезд 1     (MEMO['a-p1'])      Tour 1
        Этаж 1    (MEMO['a-p1-e1'])   Tour 2
        Этаж 2    (MEMO['a-p1-e2'])   Tour 3
    Подъезд 2     (MEMO['a-p2'])
        Этаж 1    (MEMO['a-p2-e1'])   Tour1, Tour2, Tour3
        Этаж 2    (MEMO['a-p2-e2'])
    :param api:
    :return:
    """

    # {area_id: [tour_id, tour_id, ...], ...}
    area_tours = {
        MEMO['a-p1']: [1],
        MEMO['a-p1-e1']: [2],
        MEMO['a-p1-e2']: [3],
        MEMO['a-p2-e1']: [1, 2, 3],
    }

    for area_id, tour_ids in area_tours.items():
        for tour_id in tour_ids:
            resp = api.post(
                f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{area_id}/tours',
                {'tour_id': tour_id},
                auth_as='cameraman@biganto.com'
            )
            assert resp.status_code == 200


@pytest.mark.bad_requests
def test_post_tours_bad_requests(api):
    # Пробуем добавить тот же самый тур в область и ждём отказа
    resp = api.post(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p2-e1"]}/tours',
        {'tour_id': 1},
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 400


@pytest.mark.bad_requests
def test_put_tours_bad_requests(api):
    # Переносим несуществуший там тур 1 из p1-e1 в p1-e2
    resp = api.put(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p1-e1"]}/tours/1',
        {'area_id': MEMO['a-p1-e2']},
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 404

    # Переносим тур 2 из p1-e1 в несуществующую область
    resp = api.put(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p1-e1"]}/tours/2',
        {'area_id': MEMO['a-p1-e2'] * 10000},
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 404

    # Переносим тур 3 из p1-e2 в p2-e1, где он уже есть
    resp = api.put(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p1-e2"]}/tours/3',
        {'area_id': MEMO['a-p2-e1']},
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 400


def test_put_tours(api):
    """
    PUT /projects/<id>/areas/<id>/tours/<id>
    На выходе получим такое распределение туров (в Ниф-Нифе):
    Подъезд 1     (MEMO['a-p1'])      Tour 1
        Этаж 1    (MEMO['a-p1-e1'])
        Этаж 2    (MEMO['a-p1-e2'])   Tour 2, Tour 3
    Подъезд 2     (MEMO['a-p2'])
        Этаж 1    (MEMO['a-p2-e1'])   Tour 1, Tour 2, Tour 3
        Этаж 2    (MEMO['a-p2-e2'])
    """
    # Переносим тур 2 из p1-e1 в p1-e2
    resp = api.put(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p1-e1"]}/tours/2',
        {'area_id': MEMO['a-p1-e2']},
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 200
    assert resp.result
    assert resp.result['area_id'] == MEMO['a-p1-e2']


@pytest.mark.bad_requests
def test_delete_tours_bad_requests(api):
    # Удаляем несуществующий тур
    resp = api.delete(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p1-e1"]}/tours/3',
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 404


def test_delete_tours(api):
    """
    DELETE /projects/<id>/areas/<id>/tours/<id>
    На выходе получим такое распределение туров:
    Подъезд 1     (MEMO['a-p1'])      Tour 1
        Этаж 1    (MEMO['a-p1-e1'])
        Этаж 2    (MEMO['a-p1-e2'])   Tour 2, Tour 3
    Подъезд 2     (MEMO['a-p2'])
        Этаж 1    (MEMO['a-p2-e1'])   Tour 2, Tour 3
        Этаж 2    (MEMO['a-p2-e2'])
    """
    # Удаляем Tour1 из p2-e1
    resp = api.delete(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p2-e1"]}/tours/1',
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 204


def test_get_tours(api):
    """
    Читает список туров из областей
    """
    # Читаем из одной области, без детей
    resp = api.get(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p1"]}/tours',
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 200
    assert resp.result
    assert type(resp.result) is list
    assert len(resp.result) == 1
    assert resp.result[0]['tour']['id'] == 1

    # А теперь с детками
    resp = api.get(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p1"]}/tours',
        query_string={'children': 1},
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 200
    assert resp.result
    assert type(resp.result) is list
    assert len(resp.result) == 3


def test_post_drawings(api):
    """
    POST /devcon/projects/<id>/areas/<id>/drawings
    Создаёт чертежи в Ниф-Нифе:
    Подъезд 1     (MEMO['a-p1'])      План П1
        Этаж 1    (MEMO['a-p1-e1'])   План П1-Э1
        Этаж 2    (MEMO['a-p1-e2'])   План П1-Э2, Гермиона_naked, OLD_план new
    Подъезд 2     (MEMO['a-p2'])
        Этаж 1    (MEMO['a-p2-e1'])   Каля
        Этаж 2    (MEMO['a-p2-e2'])   Баля
    """
    plans = {
        MEMO['a-p1']: ['План П1'],
        (MEMO['a-p1-e1']): ['План П1-Э1'],
        (MEMO['a-p1-e2']): ['План П1-Э2', 'Гермиона_naked', 'OLD_план new'],
        (MEMO['a-p2-e1']): ['Каля'],
        (MEMO['a-p2-e2']): ['Баля'],
    }
    for area_id, titles in plans.items():
        for title in titles:
            set_flow({'TOKEN': ['src/sample.pdf']})
            resp = api.post(
                f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{area_id}/drawings',
                {'title': title, 'file': 'flow@TOKEN/sample.pdf'},
                auth_as='plotman@biganto.com',
            )
            assert resp.status_code == 200
            assert resp.result
            MEMO['drawings'][resp.result['title']] = resp.result['id']


def test_put_drawings(api):
    """
    Меняет планировку "Баля" на "Маля" и переносит её в p2-e1
    """
    set_flow({'TOKEN': ['src/sample.pdf']})
    resp = api.put(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p2-e2"]}/drawings/{MEMO["drawings"]["Баля"]}',
        {'area_id': MEMO['a-p2-e1'], 'title': 'Маля', 'file': 'flow@TOKEN/sample.pdf'},
        auth_as='plotman@biganto.com',
    )
    assert resp.status_code == 200
    assert resp.result


def test_delete_drawings(api):
    """
    DELETE /projects/<id>/areas/<id>/drawings/<id>
    На выходе получим такое распределение чертежей в Ниф-Нифе:
    Подъезд 1     (MEMO['a-p1'])      План П1
        Этаж 1    (MEMO['a-p1-e1'])   План П1-Э1
        Этаж 2    (MEMO['a-p1-e2'])   План П1-Э2, Гермиона_naked, OLD_план new
    Подъезд 2     (MEMO['a-p2'])
        Этаж 1    (MEMO['a-p2-e1'])
        Этаж 2    (MEMO['a-p2-e2'])   Баля
    """
    # Удаляем несуществующий чертёж
    resp = api.delete(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p1-e1"]}/drawings/{MEMO["drawings"]["Каля"]}',
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 404

    # Удаляем Каля из p2-e1
    resp = api.delete(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p2-e1"]}/drawings/{MEMO["drawings"]["Каля"]}',
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 204


def test_get_drawings(api):
    """
    Читает список чертежей из областей
    """
    # Читаем из одной области, без детей
    resp = api.get(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p1"]}/drawings',
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 200
    assert resp.result
    assert type(resp.result) is list
    assert len(resp.result) == 1
    assert resp.result[0]['title'] == 'План П1'

    # А теперь с детками
    resp = api.get(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p1"]}/drawings',
        query_string={'children': 1},
        auth_as='cameraman@biganto.com',
    )
    assert resp.status_code == 200
    assert resp.result
    assert type(resp.result) is list
    assert len(resp.result) == 5


def test_get_areas(api):
    """
    GET /devcon/projects/<id>/areas
    Ответ: [DCArea, ...]
    """
    # Проверка доступа
    access = [
        (65535, 'owner@biganto.com'),  # Несуществующий проект
        (MEMO['nufnuf_id'], 'plotman@biganto.com'),  # Меня нет в проекте
    ]
    for project_id, auth_as in access:
        resp = api.get(f'/devcon/projects/{project_id}/areas', auth_as=auth_as)
        assert resp.status_code == 403 or resp.status_code == 404, (project_id, auth_as)

    resp = api.get(f'/devcon/projects/{MEMO["nifnif_id"]}/areas', auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == 6

    def find_area(areas, id_):
        """В списке [DCArea, ...] ищет область с заданным id и возвращает её"""
        for area in areas:
            if area['id'] == id_:
                return area
        return None

    assert find_area(resp.result, MEMO['a-p1'])['cnt_tours'] == 1
    assert find_area(resp.result, MEMO['a-p1-e2'])['cnt_tours'] == 2
    assert find_area(resp.result, MEMO['a-p2-e1'])['cnt_tours'] == 2

    assert find_area(resp.result, MEMO['a-p1'])['cnt_drawings'] == 1
    assert find_area(resp.result, MEMO['a-p1-e1'])['cnt_drawings'] == 1
    assert find_area(resp.result, MEMO['a-p1-e2'])['cnt_drawings'] == 3
    assert find_area(resp.result, MEMO['a-p2-e1'])['cnt_drawings'] == 1


@pytest.mark.access
def test_get_area_access(api):
    # Проверка доступа
    access = [
        (65535, False, 'owner@biganto.com'),  # Несуществующий проект
        (MEMO['nufnuf_id'], 1, 'plotman@biganto.com'),  # Меня нет в проекте
        (MEMO['nifnif_id'], MEMO['a-p2-e2'] * 100000, 'plotman@biganto.com'),  # Я есть в проекте, но области не существует
    ]
    for project_id, area_id, auth_as in access:
        resp = api.get(f'/devcon/projects/{project_id}/areas/{area_id}', auth_as=auth_as)
        assert resp.status_code == 403 or resp.status_code == 404, (project_id, area_id, auth_as)


def test_get_area(api):
    """
    GET /devcon/projects/<id>/areas/<id>
    Ответ: DCArea
    """
    resp = api.get(f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p2-e2"]}', auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert resp.result['id'] == MEMO["a-p2-e2"]
    assert resp.result['parent_id'] == MEMO["a-p2"]
    assert resp.result['title'] == 'Этажъ 2'


@pytest.mark.access
def test_put_area_access(api):
    # Проверка доступа
    access = [
        (65535, False, 'owner@biganto.com'),  # Несуществующий проект
        (MEMO['nufnuf_id'], 1, 'plotman@biganto.com'),  # Меня нет в проекте
        (MEMO['nifnif_id'], MEMO['a-p2-e2'] * 100000, 'plotman@biganto.com'),  # Я есть в проекте, но области не существует
        (MEMO['nifnif_id'], MEMO['a-p2-e2'], 'plotman@biganto.com'),  # Я есть в проекте, но я не админ
    ]
    for project_id, area_id, auth_as in access:
        resp = api.put(f'/devcon/projects/{project_id}/areas/{area_id}', {'title': 'Change'}, auth_as=auth_as)
        assert resp.status_code == 403 or resp.status_code == 404, (project_id, area_id, auth_as)


@pytest.mark.bad_requests
def test_put_area_bad_requests(api):
    # Пробуем переместить ветку своему наследнику:
    resp = api.put(f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p1"]}', {'parent_id': MEMO['a-p1-e1']}, auth_as='admin@biganto.com')
    assert resp.status_code == 400


def test_put_area(api):
    """
    PUT /devcon/projects/<id>/areas/<id>
    Ответ: DCArea
    """
    # Переименовываем область и переносим в корень дерева
    resp = api.put(
        f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p2-e2"]}',
        {'title': 'Этаж 2', 'parent_id': None, 'sort': 500},
        auth_as='admin@biganto.com'
    )
    assert resp.status_code == 200
    assert resp.result
    assert resp.result['title'] == 'Этаж 2'
    assert resp.result['sort'] == 500
    assert resp.result['parent_id'] is None

    # Возвращаем на место
    resp = api.put(f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p2-e2"]}', {'title': 'Этаж 2', 'parent_id': MEMO["a-p2"]}, auth_as='admin@biganto.com')
    assert resp.status_code == 200


def test_delete_area(api):
    """
    DELETE /devcon/projects/<id>/areas/<id>
    """
    # Удаляем область "Подъезд 2" и ждём, что удалятся и два его этажа:
    resp = api.delete(f'/devcon/projects/{MEMO["nifnif_id"]}/areas/{MEMO["a-p2"]}', auth_as='admin@biganto.com')
    assert resp.status_code == 204

    # Проверяем, что область удалилась
    resp = api.get(f'/devcon/projects/{MEMO["nifnif_id"]}/areas', auth_as='admin@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert len(resp.result) == 3


@pytest.mark.bad_requests
def test_get_projects_bad_requests(api):
    # Кривые сортировки
    for sort in ['', '-', 'zhopa', '-zhopa']:
        resp = api.get('/devcon/projects', query_string={'sort': sort}, auth_as='owner@biganto.com')
        assert resp.status_code == 400


@pytest.mark.access
def test_get_projects_access(api):
    # Читаем проект, куда у нас нет доступа
    resp = api.get(f'/devcon/projects/{MEMO["nafnaf_id"]}', auth_as='cocksucker@biganto.com')
    assert resp.status_code == 404


def test_get_projects(api):
    """
    GET /devcon/projects.
    """
    # Offset, limit, sort
    resp = api.get(
        '/devcon/projects',
        query_string={'sort': 'title', 'offset': 1, 'limit': 1, 'fields': 'cnt_members,cnt_areas,cnt_tours'},
        auth_as='owner@biganto.com'
    )
    assert resp.status_code == 200
    assert resp.result
    assert len(resp.result) == 1
    assert resp.result[0]['title'] == 'Домик Ниф-Нифа'

    # Норм запрос GET /devcon/projects, проверяем ответ
    resp = api.get('/devcon/projects', query_string={'sort': '-joined', 'fields': 'cnt_members,cnt_tours,cnt_areas'}, auth_as='owner@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert resp.result[0]['title'] == 'Домик Наф-Нафа'
    assert resp.result[0]['cnt_members'] == 2
    assert resp.result[1]['title'] == 'Домик Нуф-Нуфа'
    assert resp.result[1]['cnt_members'] == 3
    assert resp.result[2]['title'] == 'Домик Ниф-Нифа'
    assert resp.result[2]['cnt_members'] == 5

    # Норм запрос GET /devcon/projects/<id>, проверяем ответ
    resp = api.get(f'/devcon/projects/{MEMO["nafnaf_id"]}', query_string={'fields': 'cnt_members,cnt_areas,cnt_tours'}, auth_as='owner@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert resp.result['cnt_areas'] == 0
    assert resp.result['cnt_members'] == 2
    assert resp.result['cnt_tours'] == 0
    assert 'super' in resp.result['membership']['roles']


@pytest.mark.access
def test_delete_member_access(api):
    # Удаляем участника из проекта, где нас нет (Коксакером лезем в Нуф-Нуфа)
    resp = api.delete(f'/devcon/projects/{MEMO["nufnuf_id"]}/members/1', auth_as='cocksucker@biganto.com')
    assert resp.status_code == 403 or resp.status_code == 404

    # Удаляем несуществующего участника (Вьюера из Наф-Нафа)
    resp = api.delete(f'/devcon/projects/{MEMO["nafnaf_id"]}/members/5', auth_as='owner@biganto.com')
    assert resp.status_code == 404

    # Удаляем участника, где мы не админ (Камерамэном из Наф-Нафа меняем Плотмена)
    resp = api.delete(f'/devcon/projects/{MEMO["nifnif_id"]}/members/4', auth_as='cameraman@biganto.com')
    assert resp.status_code == 403


def test_delete_member(api):
    """
    DELETE /devcon/projects/<id>/members/<id>
    """
    # Нормальное удаление, удаляем хозяином вьера из Ниф-Нифа
    resp = api.delete(f'/devcon/projects/{MEMO["nifnif_id"]}/members/5', auth_as='owner@biganto.com')
    assert resp.status_code == 204

    # Проверяем, что он удалился
    resp = api.delete(f'/devcon/projects/{MEMO["nifnif_id"]}/members/5', auth_as='owner@biganto.com')
    assert resp.status_code == 404

    # Удаляем себя
    resp = api.delete(f'/devcon/projects/3/members/3', auth_as='cameraman@biganto.com')
    assert resp.status_code == 204


@pytest.mark.access
def test_delete_project_access(api):
    # Удаляем проект, где мы не owner (Админом - НифНифа)
    rv = api.delete(f'/devcon/projects/{MEMO["nifnif_id"]}', auth_as='admin@biganto.com')
    assert rv.status_code == 403 or rv.status_code == 404


def test_delete_project(api):
    """
    DELETE /devcon/projects/<id>
    """
    # Удаляем проект, где мы owner (Анной - НифНифа)
    rv = api.delete(f'/devcon/projects/{MEMO["nifnif_id"]}', auth_as='owner@biganto.com')
    assert rv.status_code == 204

    # Проверяем, что он удалился
    rv = api.get(f'/devcon/projects/{MEMO["nifnif_id"]}', auth_as='owner@biganto.com')
    assert rv.status_code == 404
