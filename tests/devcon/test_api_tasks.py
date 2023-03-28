"""
Тесты методов API Умной Стройки: задачи.
"""
import pytest
import datetime

from visual import create_app
from visual.core import db
from visual.models import DCTour
from .setup import create_users, create_projects, create_areas, create_tours

# Сторадж для передачи данных между тестами
MEMO = {
    'users': {},
    # {id: DCTask, ...}
    'tasks': {}
}


def setup_module():
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.expire_on_commit = False

        MEMO['users'] = create_users()
        create_projects()
        create_areas()
        create_tours()
        # Привязываем 1 и 2 туры к 7 области
        db.session.add(DCTour(created_by=1, tour_id=1, area_id=7))
        db.session.add(DCTour(created_by=1, tour_id=3, area_id=7))

        db.session.commit()


@pytest.mark.bad_requests
def test_post_tasks_bad_reqests(api):
    """
    POST /devcon/projects/<id>/areas/<id>/tasks.
    """
    # Плохие входные данные
    bodies = [
        {},
        {'title': 'Всё переделать'},  # Без status
        {'status': 'ты пидор'},  # Несуществующий статус
        {'status': 'archive'},  # Создавать таски можно только в draft и todo
        {'status': 'todo'},  # Без тайтла
        {'status': 'todo', 'title': ''},  # С пустым тайтлом
        {'status': 'todo', 'title': '   '},  # С пробельным тайтлом
        {'status': 'todo', 'title': None},  # С null-тайтлом
        {'status': 'todo', 'title': 'Название', 'priority': 'ты пидор'},  # Кривой priority
        {'status': 'todo', 'title': 'Название', 'deadline': 'ты пидор'},  # Кривой deadline
        {'status': 'todo', 'title': 'Название', 'assignee': False},  # Кривой assignee
        {'status': 'todo', 'title': 'Название', 'assignee': {'id': None}},  # Кривой assignee
        {'status': 'todo', 'title': 'Название', 'assignee': {'id': 100000}},  # assignee не существует
        {'status': 'todo', 'title': 'Название', 'assignee': {'id': 3}},  # assignee не имеет роли worker
        {'status': 'todo', 'title': 'Название', 'tour_id': ['bad']},  # ID тура — кривая строка
        {'status': 'todo', 'title': 'Название', 'tour_id': 100000},  # тура не существует
        {'status': 'todo', 'title': 'Название', 'tour_id': 2},  # тур не привязан к области
        {'status': 'todo', 'title': 'Название', 'tour_pos': [1, 2, 3]},  # tour_pos без tour_id
        {'status': 'todo', 'title': 'Название', 'tour_id': 1, 'tour_pos': 'bad'},  # кривой tour_pos
        {'status': 'todo', 'title': 'Название', 'tour_id': 1, 'tour_pos': [1, 2]},  # кривой tour_pos
        {'status': 'todo', 'title': 'Название', 'tour_id': 1, 'tour_pos': [1, 2, 3, 4]},  # кривой tour_pos
        {'status': 'todo', 'title': 'Название', 'tour_id': 1, 'tour_render_props': False},  # кривой tour_render_props
    ]
    for body in bodies:
        resp = api.post('/devcon/projects/1/areas/7/tasks', body, auth_as='taskman1@biganto.com')
        assert resp.status_code == 400, f'{body} - {resp.object}'


@pytest.mark.access
def test_post_tasks_access(api):
    # (auth_as, body)
    bodies = [
        # Не той ролью
        ('worker1@biganto.com', {'status': 'todo', 'title': 'Nothing'})
    ]
    for auth_as, body in bodies:
        resp = api.post(f'/devcon/projects/1/areas/7/tasks', body, auth_as=auth_as)
        assert resp.status_code in (404, 403), '{}: {}'.format(body, resp.get_data(as_text=True))


def test_post_tasks_good_reqests(api):
    """
    POST /devcon/projects/<id>/areas/<id>/tasks.
    """
    # Хорошие запросы
    # [(area_id, auth_as, body), ...]
    bodies = [
        # id=1
        (2, 'taskman2@biganto.com', {'status': 'draft', 'title': 'Раз'}),
        # id=2
        (2, 'taskman2@biganto.com', {
            'assignee': None,
            'status': 'todo',
            'title': 'Два',
            'description': 'Там где двое или трое собрались во имя Моё, там и я среди них.',
            'priority': -10,
            'deadline': '2020-08-10 12:00:00',
        }),
        # id=3
        (7, 'taskman1@biganto.com', {
            'assignee': {'id': 2},  # admin
            'status': 'todo',
            'title': 'Три',
            'priority': 0,
            'deadline': '2020-01-10 12:00',
            'tour_id': 1,
            'tour_pos': [1, 2, 3],
            'tour_render_props': {'floor': '1'}
         }),
        # id=4
        (7, 'taskman1@biganto.com', {
            'assignee': {'id': 8},  # worker1
            'status': 'todo',
            'title': 'Четыре',
            'deadline': '2020-01-10 15:00'
        }),
        # id=5
        (7, 'taskman1@biganto.com', {
            'assignee': {'id': 9},  # worker2
            'status': 'todo',
            'title': 'Пять',
            'priority': 10,
            'deadline': '2020-01-11 12:00'
        }),
        # id=6
        (7, 'taskman1@biganto.com', {
            'assignee': {'id': 9},  # worker2
            'status': 'todo',
            'title': 'Шесть',
            'priority': 20,
            'deadline': (datetime.datetime.now() + datetime.timedelta(seconds=1)).isoformat()
        }),
        # id=7
        (7, 'taskman1@biganto.com', {
            'status': 'todo',
            'title': 'Семь',
            'priority': 200,
            'deadline': (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()
        }),
        # id=8
        (7, 'taskman1@biganto.com', {
            'status': 'draft',
            'title': 'Восемь',
        }),
    ]
    for area_id, auth_as, body in bodies:
        resp = api.post(f'/devcon/projects/1/areas/{area_id}/tasks', body, auth_as=auth_as)
        assert resp.status_code == 200, '{}: {}'.format(body, resp.object)
        assert resp.result
        for key in ('status', 'title', 'description', 'priority', 'tour_id', 'tour_pos'):
            assert resp.result.get(key) == body.get(key), key
        if 'assignee' in body:
            if body['assignee'] is None:
                assert resp.result['assignee'] is None
            else:
                assert resp.result['assignee']['id'] == body['assignee']['id']
                assert resp.result['assignee']['name'] == MEMO['users'][resp.result['assignee']['id']]['name']
        if 'deadline' in body:
            if body['deadline'] is None:
                assert resp.result['deadline'] is None
            else:
                # Отбрасываем после часов
                assert resp.result['deadline'][:13] == datetime.datetime.fromisoformat(body['deadline']).isoformat()[:13]

        MEMO['tasks'][resp.result['id']] = resp.result


@pytest.mark.bad_requests
def test_put_task_bad_requests(api):
    """
    PUT /devcon/projects/<id>/areas/<id>/tasks/<id>
    """
    bad_bodies = [
        {},
        {'title': 'Всё переделать'},  # Без status
        {'status': 'ты пидор'},  # Несуществующий статус
        {'status': 'todo'},  # Без тайтла
        {'title': ''},  # С пустым тайтлом
        {'title': '   '},  # С пробельным тайтлом
        {'title': None},  # С null-тайтлом
        {'priority': 'ты пидор'},  # Кривой priority
        {'deadline': 'ты пидор'},  # Кривой deadline
        {'assignee': False},  # Кривой assignee
        {'assignee': {'id': None}},  # Кривой assignee
        {'assignee': {'id': 100000}},  # assignee не существует
        {'assignee': {'id': 3}},  # assignee не имеет роли worker
    ]
    for body in bad_bodies:
        resp = api.post('/devcon/projects/1/areas/7/tasks', body, auth_as='taskman1@biganto.com')
        assert resp.status_code == 400, f'{body} - {resp.object}'


@pytest.mark.access
def test_put_task_access(api):
    """
    Проверяет доступ к методу PUT /devcon/projects/<id>/areas/<id>/tasks
    """
    # (task_id, auth_as, body)
    bodies = [
        # Лезеем левыми людьми
        (1, 'cocksucker@biganto.com', {'title': 'changed'}),
        (1, 'cameraman@biganto.com', {'title': 'changed'}),

        # Статус
        (1, 'worker1@biganto.com', {'status': 'canceled'}),

        # Исполнителем пытаемся поменять что-нибудь кроме status
        (4, 'worker1@biganto.com', {'status': 'progress', 'title': 'Я крутой хакер!'}),

        # Меняем исполнителя
        # None -> None
        (1, 'worker1@biganto.com', {'assignee': None}),
        # Somebody -> Anotherone
        (3, 'worker1@biganto.com', {'assignee': {'id': 1}}),
        # Somebody -> Me
        (3, 'worker1@biganto.com', {'assignee': {'id': 8}}),

        # Статусы
        # Не у свой задачи
        (3, 'worker1@biganto.com', {'status': 'progress'}),
        # У своей задачи, но в запрещённый статус
        (4, 'worker1@biganto.com', {'status': 'done'}),
    ]
    for task_id, auth_as, body in bodies:
        resp = api.put(f'/devcon/projects/1/areas/7/tasks/{task_id}', body, auth_as=auth_as)
        assert resp.status_code in (404, 403), '{}: {}'.format(body, resp.get_data(as_text=True))


def test_put_task_good_requests(api):
    """
    PUT /devcon/projects/<id>/areas/<id>/tasks/<id>
    """
    # [(task_id, auth_as, body), ...]
    bodies = [
        # Пишем все свойства в задачу, где везде были None
        # area 2->3, status draft->todo, title, description, priority X->None, deadline X->None
        (1, 'taskman1@biganto.com', {
            'area_id': 3,
            'status': 'todo',
            'title': 'РАЗ',
            'description': 'БЕР',
            'priority': -100,
            'deadline': '2020-08-10 12:00:00'
        }),
        # Наоборот сбрасываем всё в None
        (2, 'taskman1@biganto.com', {
            'description': None,
            'priority': None,
            'deadline': None,
        }),

        # Меняем только одно свойство, остальные посылаем те, какие были,
        # чтобы посмотреть, что в истории не будет записи об их изменении
        (3, 'taskman1@biganto.com', {**MEMO['tasks'][3], 'description': 'Проще про трояк.'}),

        # Меняем исполнителя: 9->None, None->8, 8->9, 9->9
        (5, 'taskman1@biganto.com', {**MEMO['tasks'][5], 'assignee': None}),
        (5, 'taskman1@biganto.com', {
            'assignee': {'id': 8},
        }),
        (5, 'taskman1@biganto.com', {
            'assignee': {'id': 9},
        }),
        (5, 'taskman1@biganto.com', {
            'assignee': {'id': 9},
        }),

        # Назначаем исполнителем ничейного таска себя (первый таск ранее был переведён в todo)
        (1, 'worker1@biganto.com', {
            'assignee': {'id': 8}
        }),

        # Переводим свой таск в статус progress
        (1, 'worker1@biganto.com', {
            'status': 'progress'
        }),
    ]

    for task_id, auth_as, body in bodies:
        # resp = api.put(f'/devcon/projects/1/areas/{MEMO["tasks"][task_id]["area_id"]}/tasks/{task_id}', body, auth_as=auth_as)
        resp = api.put(f'/devcon/projects/1/tasks/{task_id}', body, auth_as=auth_as)
        assert resp.status_code == 200, '{} {}: {}'.format(auth_as, body, resp.get_data(as_text=True))
        assert resp.result
        for k, v in body.items():
            if k == 'deadline':
                if v is None:
                    assert resp.result[k] is None
                else:
                    # Отбрасываем после часов
                    assert resp.result['deadline'][:13] == datetime.datetime.fromisoformat(body['deadline']).isoformat()[:13]
            elif k == 'assignee':
                if v is None:
                    assert resp.result[k] is None
                else:
                    assert resp.result[k]['id'] == body[k]['id']
            elif k in ('updated', 'cnt_comments', 'cnt_files', 'time_task_seen'):
                continue
            else:
                assert resp.result[k] == v, k
        MEMO['tasks'][resp.result['id']] = resp.result


#
# К этому моменту есть следующие задачи:
#
# id | area | status   | creator  | assignee | title   | deadline            | priority
#  1 | 3    | progress | taskman2 | 8        | РАЗ     | 2020-08-10 12:00:00 | -100
#  2 | 2    | tdo      | taskman2 |          | Два     | null                | null
#  3 | 7    | tdo      | taskman1 | 2        | Три     | 2020-01-10 12:00:00 | 0
#  4 | 7    | tdo      | taskman1 | 8        | Четыре  | 2020-01-10 15:00:00 | null
#  5 | 7    | tdo      | taskman1 | 9        | Пять    | 2020-01-11 12:00:00 | 10
#  6 | 7    | tdo      | taskman1 | 9        | Шесть   | now + 1sec          | 20
#  7 | 7    | tdo      | taskman1 |          | Семь    | now + 1month        | 200
#  8 | 7    | draft    | taskman1 |          | Восемь  |                     |
#

def test_get_tasks_count(api):
    """
    GET /devcon/projects/<id>/tasks/count
    GET /devcon/projects/<id>/areas/<id>/tasks/count
    """
    # По всему проекту
    resp = api.get(f'/devcon/projects/1/tasks/count', auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert resp.result['progress']['past'] == [1, 0]
    assert resp.result['todo']['past'] == [3, 0]
    assert resp.result['todo']['today'] == [1, 0]
    assert resp.result['todo']['future'] == [1, 0]
    assert resp.result['todo']['notset'] == [1, 0]

    # По 7-й области
    resp = api.get(f'/devcon/projects/1/areas/7/tasks/count', auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert 'draft' not in resp.result
    assert resp.result['todo']['past'] == [3, 0]
    assert resp.result['todo']['today'] == [1, 0]
    assert resp.result['todo']['future'] == [1, 0]

    resp = api.get(f'/devcon/projects/1/areas/7/tasks/count', auth_as='taskman1@biganto.com')
    assert resp.status_code == 200
    assert 'draft' in resp.result

    # По 4-й области с детьми
    resp = api.get(f'/devcon/projects/1/areas/4/tasks/count', query_string={'children': '1'}, auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert resp.result['todo']['past'] == [3, 0]
    assert resp.result['todo']['today'] == [1, 0]
    assert resp.result['todo']['future'] == [1, 0]


@pytest.mark.access
def test_get_task_access(api):
    # Задачу в статусе Draft не должен видеть не её автор
    task_id = 8
    resp = api.get(f'/devcon/projects/1/tasks/{task_id}', auth_as='viewer@biganto.com')
    assert resp.status_code == 404, resp.object


def test_get_task(api):
    """
    GET /devcon/projects/<id>/tasks/<id>.
    """
    task_id = 7
    resp = api.get(f'/devcon/projects/1/tasks/{task_id}', auth_as='viewer@biganto.com')
    assert resp.status_code == 200, resp.object
    assert resp.result
    for k in ('id', 'title', 'description', 'priority', 'deadline'):
        assert resp.result[k] == MEMO['tasks'][task_id][k], k

    # Задачу в статусе draft должен видеть её автор
    task_id = 8
    resp = api.get(f'/devcon/projects/1/tasks/{task_id}', auth_as='taskman1@biganto.com')
    assert resp.status_code == 200, resp.object
    assert resp.result
    for k in ('id', 'title', 'description', 'priority', 'deadline'):
        assert resp.result[k] == MEMO['tasks'][task_id][k], k


@pytest.mark.bad_requests
def test_get_tasks_bad_requests(api):
    """
    GET /devcon/projects/<id>/areas/<id>/tasks
    GET /devcon/projects/<id>/tasks
    """
    # Кривой ?deadline
    resp = api.get(f'/devcon/projects/1/tasks', query_string={'sort': 'deadline', 'deadline': 'broken'}, auth_as='viewer@biganto.com')
    assert resp.status_code == 400

    resp = api.get(f'/devcon/projects/1/tasks', query_string={'sort': 'deadline', 'deadline': '=broken'}, auth_as='viewer@biganto.com')
    assert resp.status_code == 400


def test_get_tasks(api):
    """
    GET /devcon/projects/<id>/areas/<id>/tasks
    GET /devcon/projects/<id>/tasks
    """
    # Задачи 4-й области с детьми (2 шт)
    resp = api.get(f'/devcon/projects/1/areas/1/tasks', query_string={'sort': 'creator', 'children': '1'}, auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == 2

    # Забираем все задачи проекта
    resp = api.get(f'/devcon/projects/1/tasks', query_string={'sort': 'title'}, auth_as='viewer@biganto.com')
    assert resp.status_code == 200

    # Забираем все задачи проекта, deadline=today
    resp = api.get(f'/devcon/projects/1/tasks', query_string={'sort': 'deadline', 'deadline': '=today'}, auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == 1
    assert resp.result[0]['title'] == 'Шесть'

    # Забираем все задачи проекта, deadline>=today
    resp = api.get(f'/devcon/projects/1/tasks', query_string={'sort': 'deadline', 'deadline': '>=today'}, auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == 2
    assert resp.result[0]['title'] == 'Шесть'
    assert resp.result[1]['title'] == 'Семь'

    # Забираем все задачи проекта, tour_id=1
    resp = api.get(f'/devcon/projects/1/tasks', query_string={'tour_id': '1'}, auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == 1
    assert resp.result[0]['title'] == 'Три'

    resp = api.get(f'/devcon/projects/1/areas/7/tasks', query_string={'tour_id': '1'}, auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == 1
    assert resp.result[0]['title'] == 'Три'


def test_delete_task_good_requests(api):
    task_id = 5
    resp = api.delete(f'/devcon/projects/1/tasks/{task_id}', auth_as='taskman1@biganto.com')
    assert resp.status_code == 204

    resp = api.get(f'/devcon/projects/1/tasks/{task_id}', auth_as='taskman1@biganto.com')
    assert resp.status_code == 404
