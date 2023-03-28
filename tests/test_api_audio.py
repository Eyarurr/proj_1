"""
https://gitlab.biganto.com/p/docs/wikis/api3/audio
"""
import datetime
import os

import pytest

from tests.common import set_flow
from visual import create_app
from visual.core import db
from visual.models import User, AuthToken, Tour, Footage, TeamMember

USERS = {}
TOURS = {}
file1, file2 = 'audio_track_1.mp3', 'audio_track_2.mp3'


def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3 - нормальные, 4 - забаненный и 5 - удалённый
    Создаем по одному туры и по одной съемке каждому юзеру. Создаем для каждого тура директорию для ассетов
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
            tour.mkdir()

            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title')}
            TOURS[tour.id].update({'in_files': tour.in_files()})

        db.session.commit()
        db.session.close()


@pytest.mark.access
def test_access(api):
    tour_id = 1
    track_id = 'track_id'
    # Описание: Пытаемся добавить трек
    # Параметры: без токена авторизации
    # Ожидаемый результат: 403
    resp = api.put(f'/tours/{tour_id}/audio/{track_id}')
    assert resp.status_code == 403

    # Описание: Пытаемся добавить несколько треков
    # Параметры: без токена авторизации
    # Ожидаемый результат: 403
    resp = api.put(f'/tours/{tour_id}/audio')
    assert resp.status_code == 403

    # Описание: Пытаемся удалить трек
    # Параметры: без токена авторизации
    # Ожидаемый результат: 403
    resp = api.delete(f'/tours/{tour_id}/audio/{track_id}')
    assert resp.status_code == 403

    # Описание: Пытаемся удалить все треки
    # Параметры: без токена авторизации
    # Ожидаемый результат: 403
    resp = api.delete(f'/tours/{tour_id}/audio')
    assert resp.status_code == 403


def test_put_audio_track(api):
    """ 
    Изменить один трек
    PUT /tours/<tour_id>/audio/<track_id>

    Тело запроса:
    {
    'url@flow': 'TOKEN/filename',
    'title': str=null,
    'volume': float=null,
    'pause': float=null,
    'loop': bool=null
    }
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        track_id = 'audio_track_1'
        body = {'title': 'audio_track_1', 'url@flow': f'TOKEN/{file1}', 'volume': 1, 'pause': 2, 'loop': True}
        set_flow({'TOKEN': ['src/audio_track_1.mp3']})

        # Описание: Пытаемся добавить трек
        # Параметры: с токеном авторизации
        # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного и юзера может добавить клип
        resp = api.put(f'/tours/{tour_id}/audio/{track_id}', body, auth_as=user['email'])
        if user['banned']:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200
            # проверяем, что в in_files/audio есть добавляемые файлы
            list_dir = os.listdir(os.path.join(TOURS[tour_id]['in_files'], 'audio'))
            assert file1 in list_dir


def test_put_audio_tracks(api):
    """
    Изменить несколько треков
    PUT /tours/<tour_id>/audio
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        body = {
            'audio_track_1': {'title': 'audio_track_1', 'url@flow': f'TOKEN/{file1}', 'volume': 1, 'pause': 2, 'loop': True},
            'audio_track_2': {'title': 'audio_track_2', 'url@flow': f'TOKEN/{file2}', 'volume': 2, 'pause': 3, 'loop': False}
        }
        set_flow({'TOKEN': ['src/audio_track_1.mp3', 'src/audio_track_2.mp3']})

        # Описание: Пытаемся добавить несколько треков
        # Параметры: с токеном авторизации
        # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может добавить несколько клипов
        resp = api.put(f'/tours/{tour_id}/audio', body=body, auth_as=user['email'])
        if user['banned']:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200
            # проверяем, что в in_files/audio есть добавляемые файлы
            list_dir = os.listdir(os.path.join(TOURS[tour_id]['in_files'], 'audio'))
            assert file1 in list_dir and file2 in list_dir


def test_delete_track(api):
    """
    Удалить трек из фонотеки
    DELETE /tours/<tour_id>/audio/<track_id>
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        title_track = 'audio_track_1'

        # Описание: Пытаемся удалить трек
        # Параметры: с токеном авторизации
        # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может удалить клип
        resp = api.delete(f'/tours/{tour_id}/audio/{title_track}', auth_as=user['email'])
        if user['banned']:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200
            # проверяем, что нет файла в tours.in_files
            list_dir = os.listdir(os.path.join(TOURS[tour_id]['in_files'], 'audio'))
            assert file1 not in list_dir


def test_delete_tracks(api):
    """
    Удалить все треки из фонотеки
    DELETE /tours/<tour_id>/audio
    """

    for user_id, user in USERS.items():
        tour_id = user_id

        # Описание: Пытаемся удалить все треки
        # Параметры: с токеном авторизации
        # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может удалить все треки
        resp = api.delete(f'/tours/{tour_id}/audio',  auth_as=user['email'])
        if user['banned']:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 204
            # проверяем, что нет файлов в tours.in_files
            list_dir = os.listdir(os.path.join(TOURS[tour_id]['in_files'], 'audio'))
            assert file1 not in list_dir and file2 not in list_dir


@pytest.mark.bad_requests
def test_exception(api):
    """
    Плохие запросы
    """

    # Попытка добавить/изменить трек
    # Параметр: не добавлен файл в TOKEN
    tour_id = 3
    track_id = 'main.mp3'
    body = {'title': 'audio_track_1', 'url@flow': f'TOKEN/{file1}', 'volume': 1, 'pause': 2, 'loop': True}
    resp = api.put(f'/tours/{tour_id}/audio/{track_id}', body=body, auth_as='super@biganto.com')
    assert resp.status_code == 400
    resp.has_error(f'Source file TOKEN/{file1} not found for url@flow.')

    # Попытка добавить трек
    # Параметр: свойство url@flow отсутствует
    body = {'title': 'main.mp3', 'volume': 1, 'pause': 2, 'loop': True}
    resp = api.put(f'/tours/{tour_id}/audio/{track_id}', body=body, auth_as='super@biganto.com')
    assert resp.status_code == 404
    resp.has_error('URL must be specified for action \'sound\'.')

    # Попытка добавить/изменить трек
    # Параметр: свойство не существует
    body = {'title': 'audio_track_1', 'url@flow': f'TOKEN/{file1}', 'some_prop': 'some_value', 'volume': 1, 'pause': 2,
            'loop': True}
    set_flow({'TOKEN': ['src/audio_track_1.mp3']})
    resp = api.put(f'/tours/{tour_id}/audio/{track_id}', body=body, auth_as='super@biganto.com')
    assert resp.status_code == 200
    resp.has_warning('Unknown input property some_prop')

    # Попытка удалить трек
    # Параметр: Чужой тур
    tour_id = 3
    resp = api.delete(f'/tours/{tour_id}/audio/{track_id}', auth_as='anna@biganto.com')
    assert resp.status_code == 403
    resp.has_error('You can not edit this tour.')

    # Попытка удалить трек
    # Параметр: Нет такого track_id
    tour_id = 1
    resp = api.delete(f'/tours/{tour_id}/audio/{track_id}', auth_as='anna@biganto.com')
    assert resp.status_code == 400
    resp.has_error('There are no audio tracks in tour.')
