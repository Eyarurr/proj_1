"""
Тесты методов API Умной Стройки: задачи.
"""
import random
import pytest

from visual import create_app
from visual.core import db
from .setup import create_users, create_projects, create_areas, create_tasks

# Сторадж для передачи данных между тестами
MEMO = {
    # {user_id: User, ...}
    'users': {},
    # {task_id: {comment_id: DCComment, ...}, ...}
    'comments': {},
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
        create_tasks(7)

        db.session.commit()


@pytest.mark.bad_requests
def test_post_tasks_comments_bad_reqests(api):
    """
    POST /devcon/projects/<id>/tasks/<id>/comments.
    """
    # Плохие входные данные, (task_id, body)
    bodies = [
        (1, {}),
        (1, {'text': None}),
        (1, {'text': ''}),  # Пустой текст коммента
    ]
    for task_id, body in bodies:
        resp = api.post(f'/devcon/projects/1/tasks/{task_id}/comments', body, auth_as='taskman1@biganto.com')
        assert resp.status_code == 400, f'{body} - {resp.object}'


def test_post_task_comments(api):
    rqs = [
        {
            'task_id': 5,
            'authas': 'taskman1@biganto.com',
            'text': 'Ты дуся',
        },
        {
            'task_id': 5,
            'authas': 'worker1@biganto.com',
            'text': 'Нет ты сам дуся',
        },

        {
            'task_id': 2,
            'authas': 'taskman1@biganto.com',
            'text': 'Раз',
        },
        {
            'task_id': 2,
            'authas': 'taskman1@biganto.com',
            'text': 'Два',
        },
        # запрос .../tasks/1/seen. Это кривой формат, переписать, чтобы тут определялся ID задачи
        '--- SET SEEN ---',
        {
            'task_id': 2,
            'authas': 'taskman1@biganto.com',
            'text': 'Три',
        },
        {
            'task_id': 2,
            'authas': 'taskman1@biganto.com',
            'text': 'Четыре',
        },
        {
            'task_id': 2,
            'authas': 'taskman1@biganto.com',
            'text': 'Пять',
        },
    ]
    for rq in rqs:
        if rq == '--- SET SEEN ---':
            resp = api.post(f'/devcon/projects/1/tasks/2/seen', {'task': True, 'cnt_comments': 2}, auth_as='viewer@biganto.com')
            assert resp.status_code == 204
            continue

        body = {'text': rq['text']}
        resp = api.post(f'/devcon/projects/1/tasks/{rq["task_id"]}/comments', body, auth_as=rq['authas'])
        assert resp.status_code == 200, f'{body} -> {resp.object}'
        assert resp.result['task_id'] == rq['task_id']
        assert MEMO['users'][resp.result['creator']['id']]['email'] == rq['authas']
        assert resp.result['type'] == 'message'
        assert resp.result['content']['text'] == rq['text']

        MEMO['comments'].setdefault(resp.result['task_id'], {})
        MEMO['comments'][resp.result['task_id']][resp.result['id']] = resp.result


def test_get_task_comment(api):
    """
    Загружаем случайный коммент ко 2-й задаче
    """
    comment = random.choice(list(MEMO['comments'][2].values()))
    resp = api.get(f'/devcon/projects/1/tasks/{comment["task_id"]}/comments/{comment["id"]}', auth_as='worker1@biganto.com')
    assert resp.status_code == 200
    assert resp.result == comment


def test_get_task_comments(api):
    """
    Получить комментарии к задаче
    GET /devcon/projects/<id>/tasks/<id>/comments
    """
    # Загружаем все комменты ко 2-й задаче
    resp = api.get(f'/devcon/projects/1/tasks/2/comments', auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == len(MEMO['comments'][2])


def test_get_comments_count(api):
    """Проверяем счётчики комментов в DCTask и задач в DCArea"""
    # Загружаем свойства 2-й задачи и смотрим на счётчики
    resp = api.get(f'/devcon/projects/1/areas/7/tasks/2', query_string={'children': 1}, auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert resp.result['time_task_seen']
    assert resp.result['cnt_comments'] == len(MEMO['comments'][2])
    assert resp.result['cnt_comments_seen'] == 2

    # Загружаем свойства всех задач
    resp = api.get(f'/devcon/projects/1/areas/7/tasks', auth_as='viewer@biganto.com')
    for task in resp.result:
        if task['id'] == 2:
            # У второй задачи должно быть 5 комментов, два просмотрены юзером viewer, задача тоже просмотрена
            assert task['time_task_seen']
            assert task['cnt_comments'] == len(MEMO['comments'][2])
            assert task['cnt_comments_seen'] == 2

    # Получаем свойства одной области
    resp = api.get(f'/devcon/projects/1/areas/7', auth_as='viewer@biganto.com')
    assert resp.result['cnt_tasks_seen'] == 1

    # Получаем свойства всех областей
    resp = api.get(f'/devcon/projects/1/areas', auth_as='viewer@biganto.com')
    for area in resp.result:
        if area['id'] == 7:
            assert area['cnt_tasks_seen'] == 1


def test_delete_task_comment(api):
    # Удаляем первый коммент 2-й задачи
    resp = api.delete(f'/devcon/projects/1/tasks/2/comments/3', auth_as='taskman1@biganto.com')
    assert resp.status_code == 204

    # Удаляем четвёртый коммент 2-й задачи
    resp = api.delete(f'/devcon/projects/1/tasks/2/comments/7', auth_as='taskman1@biganto.com')
    assert resp.status_code == 204

    # Проверяем, что комменты удалились
    resp = api.get(f'/devcon/projects/1/tasks/5/comments/3', auth_as='taskman1@biganto.com')
    assert resp.status_code == 404
    resp = api.get(f'/devcon/projects/1/tasks/5/comments/7', auth_as='taskman1@biganto.com')
    assert resp.status_code == 404

    # Первый комментарий видел viewer@biganto.com, поэтому cnt_comments_seen должен был уменьшиться на 1
    resp = api.get(f'/devcon/projects/1/areas/7/tasks/2', auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert resp.result['cnt_comments'] == len(MEMO['comments'][2]) - 2
    assert resp.result['cnt_comments_seen'] == 1

    resp = api.get(f'/devcon/projects/1/areas/7/tasks', auth_as='viewer@biganto.com')
    for task in resp.result:
        if task['id'] == 2:
            # У второй задачи должно быть 5 комментов, два просмотрены юзером viewer, задача тоже просмотрена
            assert task['time_task_seen']
            assert task['cnt_comments'] == len(MEMO['comments'][2]) - 2
            assert task['cnt_comments_seen'] == 1
