import os
import datetime

from tests.common import set_flow
from tests.conftest import SRC_DIR
from visual import create_app
from visual.core import db
from visual.models import User, Tour, Footage, TeamMember, AuthToken
from visual.util import unzip_footage_tour

USERS = {}
TOURS = {}
file1 = '256x256.jpg'
file2 = 'image.jpg'

datasets = [
    {'id': 1, 'body': {'source@upload': f'TOKEN/{file1}'}},
    {'id': 2, 'body': {'source@upload': f'TOKEN/{file1}', 'dst_name': 'image.jpg'}
     },
]


def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3, 6 - нормальные, 4 - забаненный и 5 - удалённый
    Всем, кроме 6 добавляем подписку virtoaster-trial
    Создаем по одному туры и схемке каждому юзеру. Распаковываем ассеты в тур
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.expire_on_commit = False
        set_flow({'TOKEN': ['src/256x256.jpg']})
        users = [
            {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com'},
            {'id': 2, 'name': 'boris', 'email': 'boris@biganto.com', 'team_member': TeamMember(roles=['tours'])},
            {'id': 3, 'name': 'super', 'email': 'super@biganto.com', 'password_hash': User.hash_password('123')},
            {'id': 4, 'name': 'banned', 'email': 'banned@biganto.com', 'banned': True},
            {'id': 5, 'name': 'deleted', 'email': 'deleted@biganto.com', 'deleted': datetime.datetime.now() - datetime.timedelta(days=1)},
            {'id': 6, 'name': 'oleg', 'email': 'oleg@biganto.com'},
        ]
        for kwargs in users:
            user = User(email_confirmed=True, **kwargs)
            user.auth_tokens.append(AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30), ip='0.0.0.0'))
            db.session.add(user)
            db.session.flush()
            if user.id != 6:
                user.set_virtoaster_plan(0)
            tour = Tour(id=user.id, user_id=user.id, title='tour', footage=Footage(user_id=user.id, _status='testing', type='real'))
            db.session.add(tour)
            db.session.flush()
            tour.mkdir()
            tour.footage.mkdir()
            path = os.path.join(SRC_DIR, 'tours', 'tour-20335.zip')
            unzip_footage_tour(path, footage=tour.footage, tour=tour)

            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title')}
            TOURS[tour.id].update({'in_files': tour.in_files()})

        db.session.commit()
        db.session.close()


def test_get_files(api):
    """
    Получить список файлов в директории
    GET /tours/<tour_id>/files/<subdir>,
    GET /tours/<tour_id>/files
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        urls = [f'/tours/{tour_id}/files', f'/tours/{tour_id}/files/images']
        for url in urls:

            # Описание: попытка получить файлы
            # Параметры: без токена авторизации
            # Ожидаемый результат: Из любых туров, кроме туров удаленного, забаненного и юзера без подписки
            # 'virtoaster' можно получить файлы
            resp = api.get(url, _debug=True)
            if user['banned'] or user['deleted'] or user_id == 6:
                assert resp.status_code in (400, 403)
            else:
                assert resp.status_code == 200

            # Описание: попытка получить файлы
            # Параметры: с токеном авторизации
            # Ожидаемый результат: Любой авторизированный юзер, кроме забаненного может получить свой файлы
            resp = api.get(url, auth_as=user['email'])
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 200
                assert 'result' in resp.object


def test_put_files(api):
    """
    Загрузить файлы
    PUT /tours/<tour_id>/files/<subdir>
    PUT /tours/<tour_id>/files

    {
    "source@upload": "TOKEN/filename" | "TOKEN/*",
    "dst_name": str   // не обязательно, как назвать файл при записи
    }
    """
    for user_id, user in USERS.items():
        for dataset in datasets:
            tour_id = user_id
            urls = [f'/tours/{tour_id}/files', f'/tours/{tour_id}/files/images']
            for url in urls:

                # Описание: попытка добавить файл
                # Параметры: без токена авторизации
                # Ожидаемый результат: 403
                resp = api.put(url, body=dataset['body'])
                assert resp.status_code == 403

                # Описание: попытка добавить файл
                # Параметры: с токеном авторизации
                # Ожидаемый результат: Любой юзер, кроме забаненного может добавить себе файл
                resp = api.put(url, auth_as=user['email'], body=dataset['body'], _debug=False)
                if user['banned']:
                    assert resp.status_code == 403
                else:
                    assert resp.status_code == 200
                    # Проверим, что файла есть в response
                    list_dir = [elem['name'] for elem in resp.result]
                    if dataset['id'] == 1:
                        assert file1 in list_dir
                    else:
                        assert file2 in list_dir


def test_del_file(api):
    """
    Удалить файл
    DELETE /tours/<id>/files/<target>
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        urls = [f'/tours/{tour_id}/files/256x256.jpg', f'/tours/{tour_id}/files/images/256x256.jpg']
        for url in urls:
            # Описание: попытка удалить файл
            # Параметры: без токена авторизации
            # Ожидаемый результат: 403
            resp = api.delete(url)
            assert resp.status_code == 403

            # Описание: попытка удалить файл
            # Параметры: с токеном авторизации
            # Ожидаемый результат: Любой юзер, кроме забаненного может удалить свой файл
            resp = api.delete(url, auth_as=user['email'])
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 200
                # Проверим, что файла нет в response
                list_dir = [elem['name'] for elem in resp.result]
                assert file1 not in list_dir
