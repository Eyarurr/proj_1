import datetime

from visual.app import create_app
from flask import current_app
from visual.core import db
from visual.models import Tour, User, TeamMember, AuthToken, Footage, TourGalleryTag

USERS = {}
TOURS = {}


def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3 - нормальные, 4 - забаненный и 5 - удалённый
    Создаем по одному туры каждому юзеру. Всем кроме anna@biganto.com в тур добавляем gallery_admin = 1.
    Каждому туру добавляем GALLERY_NAV_TAGS.
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
            user.auth_tokens.append(AuthToken(signature=user.email,
                                              expires=datetime.datetime.now() + datetime.timedelta(days=30), ip='0.0.0.0'))
            db.session.add(user)
            db.session.flush()
            gallery_admin = 1 if user.id != 1 else 0
            tour = Tour(user_id=user.id, title=f'tour {user.id}', gallery_admin=gallery_admin,
                        footage=Footage(user_id=user.id, _status='published', type='real'),
                        )
            db.session.add(tour)
            db.session.flush()

            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title', 'gallery_admin')}

            GALLERY_NAV_TAGS = current_app.config.get('GALLERY_NAV_TAGS')
            for item in GALLERY_NAV_TAGS['styles'].keys():
                tag = TourGalleryTag(tour_id=tour.id, tag=f'{item}')
                db.session.add(tag)
        db.session.commit()


def test_tour_gallery(api):
    """
    Получить список туров галереи
    GET /gallery

    Get параметры
    {
        limit: Количество туров в списке. default=16
        offset: Смещение от начала списка. default=0
        fields. Какие свойства включить в ответ,
        type: Туры какого типа отдавать (real, virtual, outside). По умолчанию отдаются все туры.
        tag: Туры с каким тегом отдавать. По умолчанию отдаются все туры.
        feature: Туры с какой фичей отдавать.
        sort:
    }
    """
    query_string = {'limit': None, 'offset': None, 'fields': 'id,title,gallery_tags,footage.type', 'type': ('real',),
                    'tag': 'scandinavian', 'feature': None, 'sort': None, }

    # Описание: Пытаемся получить туры из галереи
    # Ожидаемый результат: В галерею попадают туры у которых gallery_admin=1 и туры не удаленного юзера
    # todo обычно без токена авторизации не отдаются туры удаленного и забаненного юзера
    resp = api.get(f'/gallery', query_string=query_string,)
    tours = [elem['id'] for elem in resp.result]
    assert (1, 5) not in tours
