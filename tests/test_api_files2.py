"""
Здесь проверяется работа с ассетами тура:

PUT /footages/<id>/files

Да, есть уже автотесты test_api_files.py, здесь по новой схеме всё сделано.
"""
import pytest
import os
import datetime
import filecmp

from visual import create_app
from visual.core import db
from visual.models import User,  AuthToken, Tour, Footage

USERS = {}
TOURS = {}


def setup_module():
    """
    Создаёт в пустой базе юзера:
    1. anna@biganto.com без ролей

    Каждому даёт по токену авторизации, равному User.email.

    Каждому юзеру создаются пары съёмка-тур:
    user_id*10:   'Simple'
    :return:
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
            db.session.flush()

            id_ = user.id * 10
            tour = Tour(id=id_, user_id=user.id, title='Simple', footage=Footage(id=id_, user_id=user.id, type='virtual', _status='published'))
            db.session.add(tour)

            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title')}

        db.session.commit()
        db.session.close()


def test_put_footage_files(api):
    """Пишет одиночный файл в Footage(10)/files/single.png"""
    src = os.path.join(os.path.dirname(__file__), 'src', 'panorama.png')
    with open(src, 'rb') as fh:
        source = fh.read()

    rv = api.put('/footages/10/files/single.png', auth_as='anna@biganto.com',
                 headers={
                     'Content-Type': 'application/octet-stream'
                 },
                 data=source
                 )
    assert rv.status_code == 200

    app = create_app('config.test.py')
    with app.app_context():
        footage = Footage.query.get(10)
        assert filecmp.cmp(src, footage.in_files('single.png'), shallow=False)


def test_put_footage_files_chunked(api):
    """Пишет одиночный файл в Footage(10)/files/chunked.png чанками"""
    def read_in_chunks(file_object, chunk_size):
        while True:
            data = file_object.read(chunk_size)
            if not data:
                break
            yield data

    src = os.path.join(os.path.dirname(__file__), 'src', 'panorama.png')
    total = os.stat(src).st_size

    with open(src, 'rb') as fh:
        index, offset = 0, 0
        for chunk in read_in_chunks(fh, 1000000):
            offset = index + len(chunk)
            headers = {
                'Content-Type': 'application/octet-stream',
                'Content-Range': 'bytes %d-%d/%d' % (index, offset - 1, total)
            }
            index = offset

            rv = api.put('/footages/10/files/chunked.png', auth_as='anna@biganto.com',
                         headers=headers,
                         data=chunk
                         )
            assert rv.status_code == 200
