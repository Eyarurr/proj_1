"""
todo не рассмотрен вариант добавления скайбокса в тень
"""
import os
import json
import datetime

import pytest

from visual import create_app
from visual.core import db
from visual.models import User, Footage, Tour, TeamMember, AuthToken
from visual.util import unzip_footage_tour

from .common import set_flow
from .conftest import SRC_DIR

with open(os.path.join(SRC_DIR, 'meta.json')) as fm:
    meta = json.load(fm)

datasets = {
    'put_skybox': [
        {'id': 1, 'title': 'skybox_add',
         'body': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'center', 'wurst@render_type': 'vray',
                  'pos': [1.0, 2.0, 3.0], 'q': [1, 2, 3, 4], 'floor': '1', 'title': 'title_center_vray',
                  'markerZ': 12.1,
                  }
         },
        {'id': 2, 'title': 'skybox_add',
         'body': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'left', 'wurst@render_type': 'vray',
                  'pos': [1.0, 2.0, 3.0], 'q': [1, 2, 3, 4], 'floor': '1', 'title': 'title_center_vray',
                  'disabled': False, 'markerZ': 12.1
                  }
         },
        {'id': 3, 'title': 'skybox_add',
         'body': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'right', 'wurst@render_type': 'vray',
                  'pos': [1.0, 2.0, 3.0], 'q': [1, 2, 3, 4], 'floor': '1', 'title': 'title_center_vray',
                  'disabled': False, 'markerZ': 12.1,
                  }
         },
        {'id': 4, 'title': 'skybox_add',
         'body': {'wurst@flow': 'TOKEN/panorama_binocular.png', 'wurst@eye': 'both', 'wurst@render_type': 'vray',
                  'pos': [1.0, 2.0, 3.0], 'q': [1, 2, 3, 4], 'floor': '1', 'title': 'title_center_vray',
                  'disabled': False, 'markerZ': 12.1,
                  }
         },
        {'id': 5, 'title': 'skybox_add',
         'body': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'center', 'wurst@render_type': 'corona',
                  'pos': [1.0, 2.0, 3.0], 'q': [1, 2, 3, 4], 'floor': '1', 'title': 'title_center_corona',
                  'disabled': False, 'markerZ': 12.1,
                  }
         },
        {'id': 6, 'title': 'skybox_add',
         'body': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'left', 'wurst@render_type': 'corona',
                  'pos': [1.0, 2.0, 3.0], 'q': [1, 2, 3, 4], 'floor': '1', 'title': 'title_center_corona',
                  'disabled': False, 'markerZ': 12.1
                  }
         },
        {'id': 7, 'title': 'skybox_add',
         'body': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'right', 'wurst@render_type': 'corona',
                  'pos': [1.0, 2.0, 3.0], 'q': [1, 2, 3, 4], 'floor': '1', 'title': 'title_center_corona',
                  'disabled': False, 'markerZ': 12.1,
                  }
         },
        {'id': 8, 'title': 'skybox_add',
         'body': {'wurst@flow': 'TOKEN/panorama_binocular.png', 'wurst@eye': 'both', 'wurst@render_type': 'corona',
                  'pos': [1.0, 2.0, 3.0], 'q': [1, 2, 3, 4], 'floor': '1', 'title': 'title_center_corona',
                  'disabled': False, 'markerZ': 12.1,
                  }
         },
        {'id': 1, 'title': 'skybox_modify',
         'body': {'pos': [5.0, 6.0, 7.0, 8.0], 'q': [5, 6, 7, 8], 'floor': '12', 'title': 'title_center_vray_modify',
                  'disabled': False, 'markerZ': 12.1,
                  }
         },
        {'id': 2, 'title': 'skybox_modify',
         'body': {'pos': [5.0, 6.0, 7.0, 8.0], 'q': [5, 6, 7, 8], 'floor': '12', 'title': 'title_center_vray_modify',
                  'disabled': False, 'markerZ': 12.1
                  }
         },
        {'id': 3, 'title': 'skybox_modify',
         'body': {'pos': [5.0, 6.0, 7.0, 8.0], 'q': [5, 6, 7, 8], 'floor': '12', 'title': 'title_center_vray_modify',
                  'disabled': False, 'markerZ': 12.1,
                  }
         },
        {'id': 4, 'title': 'skybox_modify',
         'body': {'pos': [5.0, 6.0, 7.0, 8.0], 'q': [5, 6, 7, 8], 'floor': '12', 'title': 'title_center_vray_modify',
                  'disabled': False, 'markerZ': 12.1,
                  }
         },
        {'id': 5, 'title': 'skybox_modify',
         'body': {'pos': [5.0, 6.0, 7.0, 8.0], 'q': [5, 6, 7, 8], 'floor': '12', 'title': 'title_center_corona_modify',
                  'disabled': False, 'markerZ': 12.1,
                  }
         },
        {'id': 6, 'title': 'skybox_modify',
         'body': {'pos': [5.0, 6.0, 7.0, 8.0], 'q': [5, 6, 7, 8], 'floor': '12', 'title': 'title_center_corona_modify',
                  'disabled': False, 'markerZ': 12.1
                  }
         },
        {'id': 7, 'title': 'skybox_modify',
         'body': {'pos': [5.0, 6.0, 7.0, 8.0], 'q': [5, 6, 7, 8], 'floor': '12', 'title': 'title_center_corona_modify',
                  'disabled': False, 'markerZ': 12.1,
                  }
         },
        {'id': 8, 'title': 'skybox_modify',
         'body': {'pos': [5.0, 6.0, 7.0, 8.0], 'q': [5, 6, 7, 8], 'floor': '12', 'title': 'title_center_corona_modify',
                  'disabled': False, 'markerZ': 12.1,
                  }
         },
    ],
    'put_skyboxes': [
        {'title': 'add_skyboxes',
         'body': {
             '151': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'center', 'wurst@render_type': 'vray',
                     'pos': [1.0, 2.0, 3.0], 'q': [1, 2, 3, 4], 'floor': '1', 'title': 'title_center_vray',
                     'disabled': False, 'markerZ': 12.1
                     },
             '152': {'wurst@flow': 'TOKEN/panorama_binocular.png', 'wurst@eye': 'both', 'wurst@render_type': 'vray',
                     'pos': [1.0, 2.0, 3.0], 'q': [1, 2, 3, 4], 'floor': '1', 'title': 'title_center_vray',
                     'disabled': False, 'markerZ': 12.1, }
         }, },

        {'title': 'modify_skyboxes',
         'body': {
             '151': {'wurst@flow': 'TOKEN/panorama.png', 'wurst@eye': 'center', 'wurst@render_type': 'vray',
                     'pos': [5.0, 6.0, 7.0], 'q': [5, 6, 7, 8], 'floor': '1', 'title': 'title_center_vray_modify',
                     'disabled': False, 'markerZ': 12.1},
             '152': {'wurst@flow': 'TOKEN/panorama_binocular.png', 'wurst@eye': 'both', 'wurst@render_type': 'vray',
                     'pos': [5.0, 6.0, 7.0], 'q': [5, 6, 7, 8], 'floor': '1', 'title': 'title_center_vray_modify',
                     'disabled': False, 'markerZ': 12.1, }
         }},
    ]
}

USERS = {}
TOURS = {}


def setup_module():
    """

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
            tour.footage.mkdir()
            path = os.path.join(SRC_DIR, 'tours', 'tour-20335.zip')
            unzip_footage_tour(path, footage=tour.footage, tour=tour)

            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title')}
            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}

        db.session.commit()
        db.session.close()


@pytest.mark.access
def test_access_skybox(api):
    for user_id, user in USERS.items():
        footage_id = user_id
        skybox_id = 1
        # Пробуем ДОБАВИТЬ скайбоксы в чужие съемки
        # ожидаемый результат: 403
        resp = api.put(f'/footages/{footage_id}/virtual/skyboxes/{skybox_id}')
        assert resp.status_code == 403

        # Пробуем УДАЛИТЬ скайбокс в чужой съемке
        # ожидаемый результат: 403
        resp = api.delete(f'/footages/{footage_id}/virtual/skyboxes/{skybox_id}')
        assert resp.status_code == 403


def test_put_skybox_add(api):
    """
    Сохранить скайбокс
    PUT /footages/<footage_id>/virtual/skyboxes/<skybox_id>
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        footage_id = user_id
        for dataset in datasets['put_skybox']:
            if dataset['title'] == 'skybox_add':
                skybox_id = dataset["id"] + 100
                params = {'auth_as': user['email'], 'body': dataset['body']}

                if dataset['id'] in (4, 8):
                    set_flow({'TOKEN': ['src/panorama_binocular.png']})
                else:
                    set_flow({'TOKEN': ['src/panorama.png']})

                #  Пробуем ДОБАВТЬ скайбоксы в свою съемку
                #  ожидаемый результат: Добавить скайбокс в съемку может любой юзер, кроме забаненного
                resp = api.put(f'/footages/{footage_id}/virtual/skyboxes/{skybox_id}', **params)
                if not user['banned']:
                    assert resp.status_code == 200
                else:
                    assert resp.status_code == 403


def test_put_skybox_modify(api):
    """
    Сохранить скайбокс
    PUT /footages/<footage_id>/virtual/skyboxes/<skybox_id>
    :param api:
    :return:
    """
    #  Пробуем ИЗМЕНИТЬ скайбоксы в съемке
    #  ожидаемый результат: Любой юзер, кроме забаненного может изменить свой скайбокс
    for user_id, user in USERS.items():
        footage_id = user_id
        for dataset in datasets['put_skybox']:
            if dataset['title'] == 'skybox_modify':
                skybox_id = dataset["id"] + 100
                params = {'auth_as': user['email'], 'body': dataset['body']}

                if dataset['id'] in (4, 8):
                    set_flow({'TOKEN': ['src/panorama_binocular.png']})
                else:
                    set_flow({'TOKEN': ['src/panorama.png']})

                resp = api.put(f'/footages/{footage_id}/virtual/skyboxes/{skybox_id}', **params)
                if not user['banned']:
                    assert resp.status_code == 200
                else:
                    assert resp.status_code == 403


def test_put_skyboxes(api):
    """
    Сохранить несколько скайбоксов
    PUT /footages/<footage_id>/virtual/skyboxes
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        footage_id = user_id
        for dataset in datasets['put_skyboxes']:
            if dataset['title'] == 'add_skyboxes':
                params = {'auth_as': user['email'], 'body': dataset['body']}

                # Пробуем ДОБАВИТЬ несколько скайбоксов себе. Любой может добавить себе список скайбоксов, кроме
                # забаненного юзера
                set_flow({'TOKEN': ['src/panorama_binocular.png', 'src/panorama.png']})
                resp = api.put(f'/footages/{footage_id}/virtual/skyboxes', **params)
                if not user['banned']:
                    assert resp.status_code == 200
                else:
                    assert resp.status_code == 403

            if dataset['title'] == 'modify_skyboxes':
                params = {'auth_as': user['email'], 'body': dataset['body']}
                # Пробуем ИЗМЕНИТЬ несколько своих скайбоксов. Любой может отредактировать свои скайбоксы списком, кроме
                # забаненного юзера
                set_flow({'TOKEN': ['src/panorama_binocular.png', 'src/panorama.png']})
                resp = api.put(f'/footages/{footage_id}/virtual/skyboxes', **params)
                if not user['banned']:
                    assert resp.status_code == 200
                else:
                    assert resp.status_code == 403


def test_del_skybox(api):
    """
    Удалить скайбокс
    DELETE /footages/<footage_id>/virtual/skyboxes/<skybox_id>
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        footage_id = user_id
        for skybox_id in range(1, 15):

            # Пробуем УДАЛИТЬ скайбокс в своей съемке
            # Ожидаемый результат: Любой может удалить скайбокс в своей съемке, кроме забаненного юзера
            resp = api.delete(f'/footages/{footage_id}/virtual/skyboxes/{skybox_id}', auth_as=user['email'])
            if not user['banned']:
                assert resp.status_code == 204
            else:
                assert resp.status_code == 403
