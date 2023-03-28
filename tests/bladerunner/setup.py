"""
Функции, вызываемые в setup_module() этой группы тестов
"""
import datetime

from visual.core import db
from visual.models import User, AuthToken, DCProject, DCMembership, DCArea, DCTask, Footage, Tour


def create_users():
    """
    Создаёт юзеров:
    1.  user@biganto.com
    10. operator1@biganto.com
    11. operator2@biganto.com
    12. operator3@biganto.com

    Возвращает словарь {user_id: {'name': User.name, 'email': User.email}, ...}
    """
    users = [
        {'id': 1, 'email': 'user@biganto.com', 'name': 'User'},
        {'id': 10, 'email': 'operator1@biganto.com', 'name': 'Operator 1'},
        {'id': 10, 'email': 'operator2@biganto.com', 'name': 'Operator 1'},
        {'id': 10, 'email': 'operator3@biganto.com', 'name': 'Operator 1'},
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


def create_tours():
    """
    Создаёт съёмки и туры:
    1. footage1/Tour 1 user_id=1
    1. footage1/Tour 2 user_id=1
    1. footage2/Tour 3 user_id=10
    :return:
    """
    footage1 = Footage(type='real', _status='published', user_id=1)
    footage2 = Footage(type='real', _status='published', user_id=1)
    db.session.add(footage1)
    db.session.add(footage2)
    tours = [
        Tour(id=1, footage=footage1, title='Tour 1 (cameraman)', user_id=1),
        Tour(id=2, footage=footage1, title='Tour 2 (cameraman)', user_id=1),
        Tour(id=3, footage=footage2, title='Tour 3 (admin)', user_id=10),
    ]
    for tour in tours:
        db.session.add(tour)
