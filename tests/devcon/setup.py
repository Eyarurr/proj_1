"""
Функции, вызываемые в setup_module() этой группы тестов
"""
import datetime

from visual.core import db
from visual.models import User, AuthToken, DCProject, DCMembership, DCArea, DCTask, Footage, Tour


def create_users():
    """
    Создаёт юзеров:
    1. owner@biganto.com. Будущий владелец проекта "Вестерос".
    2. admin@biganto.com. Будущий админ проекта.
    3. cameraman@biganto.com. Будущий съёмщик.
    4. viewer@biganto.com. Будущий просто хуй с горы.
    5. taskman1@biganto.com. Тот кто ставит задачи.
    6. taskman2@biganto.com. Тот кто ставит задачи.
    7. worker1@biganto.com. Исполнитель задач.
    8. worker2@biganto.com. Исполнитель задач.
    10. cocksucker@biganto.com. Юзер, не участвующий в проекте "Вестерос".

    Возвращает словарь {user_id: {'name': User.name, 'email': User.email}, ...}
    """
    users = [
        {'id': 1, 'email': 'owner@biganto.com', 'name': 'Owner'},
        {'id': 2, 'email': 'admin@biganto.com', 'name': 'Админ'},
        {'id': 3, 'email': 'cameraman@biganto.com', 'name': 'Съемщик'},
        {'id': 4, 'email': 'plotman@biganto.com', 'name': 'Визитёр'},
        {'id': 5, 'email': 'viewer@biganto.com', 'name': 'Визитёр'},
        {'id': 6, 'email': 'taskman1@biganto.com', 'name': 'Постановщик 1'},
        {'id': 7, 'email': 'taskman2@biganto.com', 'name': 'Постановщик 2'},
        {'id': 8, 'email': 'worker1@biganto.com', 'name': 'Исполнитель 1'},
        {'id': 9, 'email': 'worker2@biganto.com', 'name': 'Исполнитель 2'},
        {'id': 10, 'email': 'cocksucker@biganto.com', 'name': 'Левый хер'},
    ]
    result = {}
    for kwargs in users:
        user = User(email_confirmed=True, **kwargs)
        user.auth_tokens.append(
            AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30),
                      ip='0.0.0.0'))
        db.session.add(user)
        result[user.id] = {'id': user.id, 'email': user.email, 'name': user.name}

    return result


def create_projects():
    """
    Создаёт два проекта 1. Вестерос и 2. Дорн, добавляет в Вестерос преоект участников, с ролями в соответствии с их именами,
    в Дорн добавляет юзера cocksucker владельцем.
    """
    vesteros = DCProject(id=1, user_id=1, title='Вестерос')
    dorn = DCProject(id=2, user_id=10, title='Дорн')
    db.session.add(vesteros)
    db.session.add(dorn)
    db.session.flush()
    members = [
        (1, 1, ['super']), (1, 2, ['admin']), (1, 3, ['cameraman']), (1, 4, ['plotman']), (1, 5, ['viewer']),
        (1, 6, ['taskman']), (1, 7, ['taskman']), (1, 8, ['worker']), (1, 9, ['worker']),

        (2, 10, ['super'])
    ]
    for project_id, user_id, roles in members:
        db.session.add(DCMembership(project_id=project_id, user_id=user_id, roles=roles))


def create_areas(project_id=1):
    """
    Создаёт иерархию областей в проекте id=project_id
    1. Подъезд1
    2.   П1-Этаж1
    3.   П1-Этаж2
    4. Подъезд2
    5.   П2-Этаж1
    6.   П2-Этаж2
    7.     П2-Этаж2-Кв1
    8.     П2-Этаж2-Кв2
    9.     П2-Этаж2-Кв3
    :return:
    """
    areas = [
        {'id': 1, 'parent_id': None, 'title': 'П1'},
        {'id': 2, 'parent_id': 1, 'title': 'П1-Э1'},
        {'id': 3, 'parent_id': 1, 'title': 'П1-Э2'},
        {'id': 4, 'parent_id': None, 'title': 'П2'},
        {'id': 5, 'parent_id': 4, 'title': 'П2-Э1'},
        {'id': 6, 'parent_id': 4, 'title': 'П2-Э2'},
        {'id': 7, 'parent_id': 6, 'title': 'П2-Э2-К1'},
        {'id': 8, 'parent_id': 6, 'title': 'П2-Э2-К2'},
        {'id': 9, 'parent_id': 6, 'title': 'П2-Э2-К3'},
    ]
    for kwargs in areas:
        db.session.add(DCArea(created_by=1, project_id=project_id, **kwargs))


def create_tasks(area_id):
    """
    Создаёт задачи в области area_id
    id title    status      created_by     assigned_to
    1. Раз      draft       admin
    2. Два      todo        admin          worker1
    3. Три      draft       taskman1
    4. Четыре   todo        taskman1       worker1
    5. Пять     progress    taskman1       worker2
    6. Шесть    draft       taskman2
    7. Семь     todo        taskman2       worker1
    8. Восемь   progress    taskman2       worker2

    :param area_id:
    :return:
    """
    tasks = [
        {'id': 1, 'area_id': area_id, 'title': 'Раз',    'status': 'draft',    'created_by': 2},
        {'id': 2, 'area_id': area_id, 'title': 'Два',    'status': 'todo',     'created_by': 2},
        {'id': 3, 'area_id': area_id, 'title': 'Три',    'status': 'draft',    'created_by': 5},
        {'id': 4, 'area_id': area_id, 'title': 'Четыре', 'status': 'todo',     'created_by': 5, 'assigned_to': 7},
        {'id': 5, 'area_id': area_id, 'title': 'Пять',   'status': 'progress', 'created_by': 5, 'assigned_to': 8},
        {'id': 6, 'area_id': area_id, 'title': 'Шесть',  'status': 'draft',    'created_by': 6},
        {'id': 7, 'area_id': area_id, 'title': 'Семь',   'status': 'todo',     'created_by': 6, 'assigned_to': 7},
        {'id': 8, 'area_id': area_id, 'title': 'Восемь', 'status': 'progress', 'created_by': 6, 'assigned_to': 8},
    ]
    for kwargs in tasks:
        db.session.add(DCTask(**kwargs))

    area = DCArea.query.get(area_id)
    area.cnt_tasks = 8


def create_tours():
    """
    Создаёт съёмки и туры:
    1. footage1/Tour 1 user_id=3
    1. footage1/Tour 2 user_id=3
    1. footage2/Tour 3 user_id=2
    :return:
    """
    footage1 = Footage(type='real', _status='published', user_id=3)
    footage2 = Footage(type='real', _status='published', user_id=2)
    db.session.add(footage1)
    db.session.add(footage2)
    tours = [
        Tour(id=1, footage=footage1, title='Tour 1 (cameraman)', user_id=3),
        Tour(id=2, footage=footage1, title='Tour 2 (cameraman)', user_id=3),
        Tour(id=3, footage=footage2, title='Tour 3 (admin)', user_id=2),
    ]
    for tour in tours:
        db.session.add(tour)
