"""
https://gitlab.biganto.com/p/docs/wikis/api3/actions
"""
import datetime
import pytest

from tests.common import set_flow
from visual import create_app
from visual.core import db
from visual.models import User, TeamMember, AuthToken, Tour, Footage

datasets = {
    'actions': [
        {
            'id': 1, 'action': 'goto_action',
            'body': {
                'type': 'goto', 'skybox': 1, 'skybox_offset': 2, 'q': [1, 1, 1, 1], 'duration': 5, 'name': 'Action_goto'
            }
        },
        {
            'id': 2, 'action': 'popup_action',
            'body': {
                'type': 'popup', 'html': 'html', 'html_get': None, 'iframe': None, 'image@flow': None, 'title': None,
                'body': None, 'buttons': None
            }
        },
        {
            'id': 3, 'action': 'popup_action',
            'body': {
                'type': 'popup', 'html': None, 'html_get': 'html_get', 'iframe': None, 'image@flow': None,
                'title': None, 'body': None, 'buttons': None
            }
        },
        {
            'id': 4, 'action': 'popup_action',
            'body': {
                'type': 'popup', 'html': None, 'html_get': None, 'iframe': 'iframe', 'image@flow': None, 'title': None,
                'body': None, 'buttons': None
            }
        },
        {
            'id': 5, 'action': 'popup_action',
            'body': {
                'type': 'popup', 'html': None, 'html_get': None, 'iframe': None, 'image@flow': None, 'title': "None",
                'body': 'BODY', 'buttons': []
            }
        },
        {
            'id': 6, 'action': 'popup_action',
            'body': {
                'type': 'popup', 'html': None, 'html_get': None, 'iframe': None, 'title': None, 'body': None,
                'buttons': None, 'image@flow': 'TOKEN/1-1.jpg'
            }
        },
        {
            'id': 7, 'action': 'sound_action',
            'body': {
                'type': 'sound', 'name': 'Action_sound', "url": 'http://qwe.mp3'
            }
        },
        {
            'id': 8, 'action': 'href_action',
            'body': {
                'type': 'href', 'name': 'Action_href', "url": 'http://google.com', 'target': '_blank'
            }
        },
        {
            'id': 9, 'action': 'video_action',
            'body': {
                'type': 'video', 'name': 'Action_video', 'size': ["60%", "50%"], 'urls': {'avi': 'video_files.avi'}
            }
        },
        {
            'id': 10, 'action': 'tour_action',
            'body': {
                'type': 'tour', 'id': '1', 'name': 'Action_tour', 'keep_position': True, 'skybox': '1',
                'q': [1, 1, 1, 1], 'target': '_blank'
            }
        },
        {
            'id': 11, 'action': 'clickable_toggle_class_action',
            'body': {
                'type': 'clickable_toggle_class', 'name': 'Action_clickable_toggle_class_action', 'class': 'text'
            }
        },
        {
            'id': 12, 'action': 'shadow_action',
            'body': {
                'type': 'shadow', 'selection': ['asd'], 'cycle': True, 'mode': 'random', 'name': 'Action_shadow'
            }
        },
        {
            'id': 13, 'action': 'offer_action',
            'body': {
                'type': 'offer', 'name': 'Action_offer', 'id': '1', 'tour_id': '1', 'q': None, 'skybox': None,
                'target': '_blank',
            }
        }
    ]
}

USERS = {}
TOURS = {}


def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3 - нормальные, 4 - забаненный и 5 - удалённый
    Создаем по одному туры каждому юзеру.
    :return:
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

            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title')}

        db.session.commit()
        db.session.close()


@pytest.mark.access
def test_post_action_access(api):
    """
    Добавить экшен POST /tours/<tour_id>/actions
    """
    # Авторизованные юзеры пытаются добавить экшены из dataset['actions'] в свой тур
    # Ожидаемый результат: все авторизованные юзеры могут добавить себе все экшены
    # Забаненый юзер не может добавлять экшены
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['actions']:
            set_flow({'TOKEN': ['src/1-1.jpg']})
            resp = api.post(f'/tours/{tour_id}/actions', body=dataset['body'], auth_as=user['email'])
            if user['banned']:
                assert resp.status_code == 403, f'{user["email"]} - {dataset["body"]} - {resp.result}'
            else:
                assert resp.status_code == 200, f'{user["email"]} - {dataset["body"]} - {resp.result}'


@pytest.mark.access
def test_get_actions_access(api):
    """
    Получим список экшенов в туре для каждого юзера
    GET /tours/<tour_id>/actions
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        resp = api.get(f'/tours/{tour_id}/actions', auth_as=user['email'])
        if user['banned']:
            assert resp.status_code == 403, f'{user["email"]} - {resp.result}'
        else:
            assert resp.status_code == 200, f'{user["email"]} - {resp.result}'


def test_put_action(api):
    """
    Изменить экшен
    PUT /tours/<tour_id>/actions/<action_id>
    """
    # Авторизованные юзеры пытаются изменить экшены из datasets['actions'] в своём туре
    # Ожидаемый результат: все авторизованные юзеры могут изменять свои все экшены
    # Забаненый юзер не может добавлять экшены
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['actions']:
            if dataset['action'] == 'popup_action':
                set_flow({'TOKEN': ['src/1-1.jpg']})
            name = dataset['body']['type'] + '_new name'
            dataset['body']['name'] = name

            # Пробуем изменить экшен
            # Ожидаемый результат: любой юзер, кроме забаненого может поменять экшен
            resp = api.put(f'/tours/{tour_id}/actions/{dataset["id"]}', body=dataset['body'], auth_as=user['email'])
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 200

            # Пробуем добавить экшен
            # Ожидаемый результат: любой юзер, кроме забаненого может добавить экшен
            if dataset['action'] == 'popup_action':
                set_flow({'TOKEN': ['src/1-1.jpg']})
            resp = api.put(f'/tours/{tour_id}/actions/{dataset["id"] + 100}', body=dataset['body'],
                           auth_as=user['email'])
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 200


def test_del_action(api):
    """
    Удалить экшен
    DELETE /tours/<tour_id>/actions/<action_id>
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        # Пробуем удалить экшен
        # Ожидаемый результат: любой юзер, кроме забаненого может удалить экшен
        resp = api.delete(f'/tours/{tour_id}/actions/1', auth_as=user['email'])
        if not user['banned']:
            assert resp.status_code == 204
        else:
            assert resp.status_code == 403


@pytest.mark.bad_requests
def test_exception(api):
    """
    :param api:
    :return:
    """
    # Получить несуществующий экшен тура
    tour_id = 3
    action_id = '1000'
    resp = api.get(f'/tours/{tour_id}/actions/{action_id}', auth_as='super@biganto.com')
    assert resp.status_code == 404
    assert resp.has_error(f'Action "{action_id}" not found.')

    # Указан неверный тип изменяемого экшена
    action_id = '2'
    simple_dataset = {'type': 'goto', 'skybox': '10', 'name': 'Action_1', 'skybox_offset': None, 'q': [1, 2, 3, 1],
                      'duration': 20, }
    resp = api.put(f'/tours/{tour_id}/actions/{action_id}', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('You can not change action type.')

    # Указан неверный тип добавляемого экшена
    action_id = '30'
    simple_dataset = {'type': 'BAD_TYPE', 'skybox': '10', 'name': 'Action_1', 'skybox_offset': None, 'q': [1, 2, 3, 1],
                      'duration': 20, }
    resp = api.put(f'/tours/{tour_id}/actions/{action_id}', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Unknown action type.')

    # Некорректное сочетание свойств: у экшена типа popup не может быть одновременно свойств html и iframe
    simple_dataset = {'type': 'popup', 'html': 'asdasd', 'iframe': 'asd.html', 'bg': [0, 0, 0, 100],
                      'size': ["60%", "50%"], }
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Popup action should contain either')

    # Некорректное значение свойства
    simple_dataset = {'type': 'popup', 'iframe': 'http://asd.aa', 'bg': [0, 0, 0, 100], 'size': 1, }
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400

    # Некорректное значение свойства
    simple_dataset = {'type': 'HELLO', 'iframe': 'http://asd.aa', 'bg': [0, 0, 0, 100], 'size': 1, }
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Unknown action type.')

    # popup: Некорректное значение свойства
    simple_dataset = {'type': 'popup', 'iframe': 'http://asd.aa', 'bg': [0, 0, 0, 100], 'size': 1, }
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Bad data type for property size')

    # popup: Некорректное значение свойства
    simple_dataset = {'type': 'HELLO', 'iframe': 'http://asd.aa', 'bg': [0, 0, 0, 100], 'size': 1, }
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Unknown action type.')

    # не существующее свойство
    simple_dataset = {'type': 'popup', 'iframe': 'http://asd.aa', 'bg': [0, 0, 0, 100], 'size': ["60%", "50%"],
                      'shit': 'shit'}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 200
    assert resp.has_warning('Unknown input property')

    # popup: нет файла в TOKEN
    simple_dataset = {'type': 'popup', 'iframe': 'http://asd.aa', 'bg': [0, 0, 0, 100], 'size': ["60%", "50%"],
                      'image@flow': 'TOKEN/1-1.jpg'}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Popup action should contain either')

    # popup: Неверное расширение файла
    simple_dataset = {'type': 'popup', 'bg': [0, 0, 0, 100], 'size': ["60%", "50%"], 'image@flow': 'TOKEN/1-1.img'}
    set_flow({'TOKEN': ['src/1-1.img']})
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 404
    assert resp.has_error('Unsupported image extension')

    # popup: Файл не изображение
    simple_dataset = {'type': 'popup', 'bg': [0, 0, 0, 100], 'size': ["60%", "50%"], 'image@flow': 'TOKEN/not_img.jpg'}
    set_flow({'TOKEN': ['src/not_img.jpg']})
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 404
    assert resp.has_error('Unknown image type')

    # popup: Размер файла превышает допустимый: 5mb
    simple_dataset = {'type': 'popup', 'bg': [0, 0, 0, 100], 'size': ["60%", "50%"], 'image@flow': 'TOKEN/panorama.png'}
    set_flow({'TOKEN': ['src/panorama.png']})
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 404
    assert resp.has_error('File size should not exceed')

    # Попытка создать экшен с ошибочными свойствами sound
    simple_dataset = {'type': 'sound'}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('URL must be specified for action "sound".')

    # sound не существующее свойство
    simple_dataset = {'type': 'sound', 'url': {'asd': 'sda'}, 'shit': {'asd': 'sda'}}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 200
    assert resp.has_warning('Unknown input property')

    # Попытка добавить video экшен без url
    simple_dataset = {'type': 'video', 'name': 'video', 'size': ["60%", "50%"], }
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400, resp.object
    assert resp.has_error('Video URLs must be specified')

    # Попытка создать экшен с ошибочными свойствами sound
    simple_dataset = {'type': 'sound', }
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('URL must be specified for action "sound".')

    # sound не существующее свойство
    simple_dataset = {'type': 'sound', 'url': {'asd': 'sda'}, 'shit': {'asd': 'sda'}}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 200
    assert resp.has_warning('Unknown input property')

    # Попытка добавить video экшен с плохими данными
    simple_dataset = {'type': 'video', 'name': 'video', 'size': ["60%", "50%"]}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Video URLs must be specified for action "video".')

    # video Неверное значение свойства
    simple_dataset = {'type': 'video', 'name': 'video', 'size': ["60%", "50%"], 'urls': 'asd'}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Invalid urls value')

    # video Внутри свойства неверное оформление
    simple_dataset = {'type': 'video', 'name': 'video', 'size': [123, {"50%"}], 'urls': {'asd': 'asdasd'}}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Malformed size value.')

    # video urls не должен быть пустым
    simple_dataset = {'type': 'video', 'name': 'video', 'size': ["50%", "50%"], 'urls': {}}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('You must specify at least one URL for video action.')

    # video не существующее свойство
    simple_dataset = {'type': 'video', 'name': 'video', 'size': ["60%", "50%"], 'shit': 'asd',
                      'urls': {'asd': 'asdasd'}}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 200
    assert resp.has_warning('Unknown input property shit')

    # video urls не должен быть пустым
    simple_dataset = {'type': 'video', 'name': 'video', 'size': ["50%", "50%"], 'urls': {}}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('You must specify at least one URL for video action.')

    # video не существующее свойство
    simple_dataset = {'type': 'video', 'name': 'video', 'size': ["60%", "50%"], 'shit': 'asd',
                      'urls': {'asd': 'asdasd'}}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 200
    assert resp.has_warning('Unknown input property ')

    # Попытка создать экшен с ошибочными свойствами href
    simple_dataset = {'type': 'href', 'name': 'href', }
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('URL must be specified for action "href".')

    # href Внутри свойства неверное оформление
    simple_dataset = {'type': 'href', 'name': 'href', 'url': '', 'target': ''}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Malformed target value.')

    # Попытка создать экшен с ошибочными свойствами tour
    simple_dataset = {'type': 'tour', 'name': 'tour', 'keep_position': True, 'skybox': '1', 'q': [1, 1, 1, 1],
                      'target': '_blank'}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Tour ID must be specified for action "tour".')

    # href Неверный тип свойства
    simple_dataset = {'type': 'tour', 'id': '1', 'name': 'tour', 'keep_position': True, 'skybox': '1',
                      'q': [[1], (1), 1, 1], 'target': '_blank'}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Bad data type for property')

    # href # Неверное значение свойства
    simple_dataset = {'type': 'tour', 'id': '1', 'name': 'tour', 'keep_position': True, 'skybox': '1',
                      'q': [1, 1, 1, 1], 'target': 'shit'}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Malformed target value.')

    # href не существующее свойство
    simple_dataset = {'type': 'tour', 'id': '1', 'keep_position': None, 'name': 'tour', 'skybox': None, 'shit': None, }
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 200
    assert resp.has_warning('Unknown input property')

    # Попытка создать экшен с ошибочными свойствами goto
    simple_dataset = {'type': 'goto', 'name': 'Action_1', 'skybox_offset': None, 'q': None, 'duration': None}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Target skybox must be specified for action "goto".')

    # goto: Неверный тип свойства
    simple_dataset = {'type': 'goto', 'skybox': '10', 'name': 'Action_1', 'skybox_offset': None, 'q': [1, 2, 3, 1],
                      'duration': 'str'}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Bad data type for property')

    # goto: не существующее свойство
    simple_dataset = {'type': 'goto', 'skybox': '10', 'name': 'Action_1', 'skybox_offset': None, 'q': [1, 2, 3, 1],
                      'duration': 20, 'shit': 'str'}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 200
    assert resp.has_warning('Unknown input property ')

    # shadow: не верный тип значения свойства
    simple_dataset = {'type': 'shadow', 'name': 'Action_shadow', 'selection': 123}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error("Bad data type for  property selection")

    # shadow: не верный тип свойства
    simple_dataset = {'type': 'shadow', 'name': 'Action_shadow', 'mode': 'hello'}
    resp = api.post(f'/tours/{tour_id}/actions', simple_dataset, auth_as='super@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error("Bad data type for property")

    # удалить не существующий экшен
    tour_id = 3
    action_id = '150'
    resp = api.delete(f'/tours/{tour_id}/actions/{action_id}', auth_as='super@biganto.com')
    assert resp.status_code == 404
    assert resp.has_error('Action "150" not found.')


def test_del_actions(api):
    """
    Удалить все экшены
    DELETE /tours/<tour_id>/actions
    :param api:
    :return:
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        # Пробуем удалить все экшены
        # Ожидаемый результат: любой юзер, кроме забаненого может удалить экшен
        rv = api.delete(f'/tours/{tour_id}/actions', auth_as=user['email'])
        if not user['banned']:
            assert rv.status_code == 204
        else:
            assert rv.status_code == 403
