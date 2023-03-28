"""
Тесты методов API Умной Стройки: задачи.
"""
import pytest

from visual import create_app
from visual.core import db
from ..common import set_flow
from .setup import create_users, create_projects, create_areas, create_tasks

# Сторадж для передачи данных между тестами
MEMO = {
    # task_id: [DCTaskFile, ...]
    'files': {}
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


@pytest.mark.access
def test_post_task_files_access(api):
    set_flow({
        'TOKEN': ['src/meta.json']
    })
    # auth_as, task_id, body
    bodies = [
        # Не член проекта
        ('cocksucker@biganto.com', 4, {'file': 'TOKEN/meta.json'}),
        # worker в несуществующую задачу
        ('worker1@biganto.com', 666, {'file': 'TOKEN/meta.json'}),
        # Не admin/taskman/worker
        ('viewer@biganto.com', 4, {'file': 'TOKEN/meta.json'}),
        # worker в задачу, где он не исполнитель
        ('worker1@biganto.com', 5, {'file': 'TOKEN/meta.json'}),
    ]
    for auth_as, task_id, body in bodies:
        resp = api.post('/devcon/projects/1/tasks/{task_id}/files', body, auth_as=auth_as)
        assert resp.status_code in (404, 403), '{}: {}'.format(body, resp.object)


@pytest.mark.bad_requests
def test_post_task_files_bad_requests(api):
    # Плохие входные данные
    bodies = [
        {}, None, False, '', 1,
        [[]], [None], [False], [''], [1],
        [{'file': 'Тут хуйня'}],
        [{'file': 'flow@badtoken'}],
        [{'file': 'flow@badtoken/badfile'}],
        [{'file': 'dataurl@broken'}],
    ]
    for body in bodies:
        resp = api.post('/devcon/projects/1/tasks/4/files', body, auth_as='taskman1@biganto.com')
        assert resp.status_code == 400, '{}: {}'.format(body, resp.object)


def test_post_task_files(api):
    set_flow({
        'TOKEN': ['src/1536x1536.jpg', 'src/1-1.jpg', 'src/meta.json', 'src/panorama.png']
    })
    # (task_id, auth_as, body)
    bodies = [
        # Админ добавляет файл в свою задачу
        (2, 'admin@biganto.com', [{'file': 'flow@TOKEN/meta.json'}]),

        # Админ добавляет файл в чужую задачу
        (5, 'admin@biganto.com', [{'file': 'flow@TOKEN/meta.json'}]),

        # Taskman добавляет файл в чужую задачу
        (7, 'taskman1@biganto.com', [{'file': 'flow@TOKEN/meta.json'}]),

        # Владелец задачи добавляет файл, картинку
        (4, 'taskman1@biganto.com', [{'file': 'flow@TOKEN/1536x1536.jpg'}]),

        # Исполнитель задачи добавляет файл, текст с подписью
        (4, 'worker1@biganto.com', [{'file': 'flow@TOKEN/meta.json', 'title': 'Какая-то jsonина'}]),

        # Тут set-seen
        (4, 'viewer@biganto.com', 'SEEN'),

        # Исполнитель задачи добавляет несколько файлов, один файл дважды
        (
            4, 'worker1@biganto.com',
            [
                {'file': 'flow@TOKEN/1-1.jpg', 'title': 'Групповая загрузка 1'},
                {'file': 'flow@TOKEN/meta.json', 'title': 'Групповая загрузка 2'},
                {'file': 'flow@TOKEN/meta.json', 'title': 'Групповая загрузка 3'},
            ]
        ),
    ]
    for task_id, auth_as, body in bodies:
        if body == 'SEEN':
            resp = api.post(f'/devcon/projects/1/tasks/{task_id}/seen', {'cnt_files': 2}, auth_as='viewer@biganto.com')
            assert resp.status_code == 204
            continue

        resp = api.post(f'/devcon/projects/1/tasks/{task_id}/files', body, auth_as=auth_as)
        assert resp.status_code == 200, '{}: {}'.format(body, resp.get_data(as_text=True))
        assert resp.result
        MEMO['files'].setdefault(task_id, [])
        MEMO['files'][task_id] += resp.result


def test_get_task_files(api):
    resp = api.get(f'/devcon/projects/1/tasks/4/files', auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert resp.result == MEMO["files"][4]

    # Проверяем сортировку
    resp = api.get(
        f'/devcon/projects/1/tasks/4/files', query_string={'sort': '-created', 'offset': 1, 'limit': 3},
        auth_as='viewer@biganto.com'
    )
    assert resp.status_code == 200
    assert len(resp.result) == 3
    assert resp.result[0]['id'] == MEMO['files'][4][3]['id']
    assert resp.result[0]['file']['name'] == MEMO['files'][4][3]['file']['name']
    assert resp.result[1]['id'] == MEMO['files'][4][2]['id']
    assert resp.result[2]['id'] == MEMO['files'][4][1]['id']


def test_get_task_file(api):
    # Читаем первый файл в задаче id=4
    resp = api.get(f'/devcon/projects/1/tasks/4/files/{MEMO["files"][4][0]["id"]}', auth_as='taskman1@biganto.com')
    assert resp.status_code == 200
    assert resp.result == MEMO["files"][4][0]

    # Проверяем скачивание файла
    download = api.get(resp.result['file']['url'].replace('/api/v3', ''), auth_as='taskman1@biganto.com')
    assert download.status_code == 200
    assert download.headers['Content-Disposition'].startswith('inline')
    assert download.headers['Content-Type'] == 'image/jpeg'

    download = api.get(resp.result['file']['url'].replace('/api/v3', ''), auth_as='taskman1@biganto.com', query_string={'attachment': 1})
    assert download.status_code == 200
    assert download.headers['Content-Disposition'] == 'attachment; filename=1536x1536.jpg'


def test_get_files_count(api):
    """Проверяем счётчики комментов в DCTask и задач в DCArea"""
    # Загружаем свойства 2-й задачи и смотрим на счётчики
    resp = api.get(f'/devcon/projects/1/areas/7/tasks/4', query_string={'children': 1}, auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert resp.result['time_task_seen'] is None
    assert resp.result['cnt_files'] == len(MEMO['files'][4])
    assert resp.result['cnt_files_seen'] == 2

    # Загружаем свойства всех задач
    resp = api.get(f'/devcon/projects/1/areas/7/tasks', auth_as='viewer@biganto.com')
    for task in resp.result:
        if task['id'] == 4:
            # У второй задачи должно быть 5 комментов, два просмотрены юзером viewer, задача тоже просмотрена
            assert task['time_task_seen'] is None
            assert task['cnt_files'] == len(MEMO['files'][4])
            assert task['cnt_files_seen'] == 2

    # Получаем свойства одной области
    resp = api.get(f'/devcon/projects/1/areas/7', auth_as='viewer@biganto.com')
    assert resp.result['cnt_tasks_seen'] == 0

    # Получаем свойства всех областей
    resp = api.get(f'/devcon/projects/1/areas', auth_as='viewer@biganto.com')
    for area in resp.result:
        if area['id'] == 7:
            assert area['cnt_tasks_seen'] == 0


@pytest.mark.bad_requests
def test_delete_task_file_bad_requests(api):
    # Удаляем несуществующий файл в задаче id=4 и убеждаемся, что его больше нет
    resp = api.delete(f'/devcon/projects/1/tasks/4/files/666', auth_as='taskman1@biganto.com')
    assert resp.status_code == 404, resp.object


def test_delete_task_file(api):
    # Удаляем первый файл в задаче id=4 и убеждаемся, что его больше нет
    resp = api.delete(f'/devcon/projects/1/tasks/4/files/{MEMO["files"][4][0]["id"]}', auth_as='taskman1@biganto.com')
    assert resp.status_code == 204

    # Удаляем пятый файл в задаче id=4 и убеждаемся, что его больше нет
    resp = api.delete(f'/devcon/projects/1/tasks/4/files/{MEMO["files"][4][4]["id"]}', auth_as='taskman1@biganto.com')
    assert resp.status_code == 204

    # Проверяем, что файлы удалились
    resp = api.get(f'/devcon/projects/1/tasks/4/files/{MEMO["files"][4][0]["id"]}', auth_as='taskman1@biganto.com')
    assert resp.status_code == 404
    resp = api.get(f'/devcon/projects/1/tasks/4/files/{MEMO["files"][4][4]["id"]}', auth_as='taskman1@biganto.com')
    assert resp.status_code == 404

    # Первый файл видел viewer@biganto.com, поэтому cnt_comments_seen должен был уменьшиться на 1
    resp = api.get(f'/devcon/projects/1/areas/7/tasks/4', auth_as='viewer@biganto.com')
    assert resp.status_code == 200
    assert resp.result['cnt_files'] == len(MEMO['files'][4]) - 2
    assert resp.result['cnt_files_seen'] == 1
