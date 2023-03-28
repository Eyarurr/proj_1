import datetime
import pytest

from visual import create_app
from visual.core import db
from visual.models import Estate, User, AuthToken, Tag, EstateTag

tags = [
    {'name': 'type', 'display_dict': {'1': 'Квартира', '2': 'Комната'}, 'label': 'Некое описание тега'},
    {'name': 'price', 'suffix': ' USD', 'label': 'Некое описание тега'},
    {'name': 'metro', 'prefix': 'м.', 'label': 'Горки'},
    {'name': 'metro', 'prefix': 'м.', 'label': 'Аметьево'},
    {'name': 'area', 'suffix': 'кв.м', 'label': 'Некое описание тега'},
    {'name': 'finishing', 'display_dict': {'1': 'Без отделки', '2': 'Евроремонт'}, 'label': 'Некое описание тега'}
]
USERS = {}


def setup_module():
    """
    Добавим одного юзера и один Эстейт ему
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

            estate = Estate(user_id=user.id, title=f'Объект_{user.id}')
            db.session.add(estate)
            db.session.flush()
            for val in tags:
                tag = Tag(user_id=user.id, **val)
                db.session.add(tag)
                db.session.flush()
                e_tag = EstateTag(estate_id=estate.id, tag_id = tag.id, value = f'value_{tag.id}')
                db.session.add(e_tag)
            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            db.session.commit()


def test_post_tag(api):
    """
    POST /estates/<id>/tags
    """
    for user_id, user in USERS.items():
        estate_id = user_id
        body = {
            'name': 'metro',
            'value': 'Сокол'
        }
        resp = api.post(f'/estates/{estate_id}/tags', body, auth_as=user['email'])
        assert resp.status_code == 200


def test_get_tags(api):
    """
    GET /estates/<id>/tags
    Параметры Query String:
        name: name=area,floor
        format_values=1
        group_tags=id|name
    """
    for user_id, user in USERS.items():
        estate_id = user_id

        # без queue_string
        resp = api.get(f'/estates/{estate_id}/tags', auth_as=user['email'])
        assert resp.status_code == 200

        qs = {'format_values': 1}
        resp = api.get(f'/estates/{estate_id}/tags', auth_as=user['email'], query_string=qs)
        assert resp.status_code == 200
        for tag in resp.result:
            assert 'display_dict' not in tag

        qs = {'name': 'metro,price'}
        resp = api.get(f'/estates/{estate_id}/tags', auth_as=user['email'], query_string=qs)
        assert resp.status_code == 200
        for tag in resp.result:
            assert tag['name'] in ('metro', 'price')

        qs = {'group_tags': 'id'}
        resp = api.get(f'/estates/{estate_id}/tags', auth_as=user['email'], query_string=qs)
        assert resp.status_code == 200
        assert type(resp.result) is dict
        assert list(resp.result.keys()) == ['1', '2', '3', '4', '5', '6']

        qs = {'group_tags': 'name'}
        resp = api.get(f'/estates/{estate_id}/tags', auth_as=user['email'], query_string=qs)
        assert resp.status_code == 200
        assert type(resp.result) is dict
        assert list(resp.result.keys()) == ['area', 'finishing', 'metro', 'price', 'type']


def test_get_tag_name(api):
    """
    GET /estates/<id>/tags/<name>
    """
    tags_name = ['area', 'finishing', 'metro', 'price', 'type']
    for user_id, user in USERS.items():
        estate_id = user_id
        tag_name = tags_name[0]
        resp = api.get(f'/estates/{estate_id}/tags/{tag_name}', auth_as=user['email'])
        assert resp.status_code == 200
        for val in resp.result:
            assert val['name'] == tag_name


def test_get_tag_id(api):
    """
    GET /estates/<id>/tags/<id>
    """
    for user_id, user in USERS.items():
        estate_id = user_id
        tag_id = user_id
        resp = api.get(f'/estates/{estate_id}/tags/{tag_id}', auth_as=user['email'])
        assert resp.status_code == 200
        assert resp.result['id'] == tag_id


def test_put_tag(api):
    """
    PUT /estates/<id>/tags/<id>
    """
    for user_id, user in USERS.items():
        estate_id = user_id
        tag_id = user_id
        body = {'value': 'new_value'}
        resp = api.put(f'/estates/{estate_id}/tags/{tag_id}', body, auth_as=user['email'])
        assert resp.status_code == 200
        assert resp.result['value'] == body['value']


def test_del_tag_name(api):
    """
    DELETE /estates/<id>/tags/<name>
    """
    for user_id, user in USERS.items():
        estate_id = user_id
        name = 'metro'
        resp = api.delete(f'/estates/{estate_id}/tags/{name}', auth_as=user['email'])
        assert resp.status_code == 204
        # Проверим, что удалился. Запрос на получение иега по имени должен быть пустой
        resp = api.get(f'/estates/{estate_id}/tags/{name}', auth_as=user['email'])
        assert not resp.result


def test_del_tag_id(api):
    for user_id, user in USERS.items():
        estate_id = user_id
        id = 5
        resp = api.delete(f'/estates/{estate_id}/tags/{id}', auth_as=user['email'])
        assert resp.status_code == 204
        # Проверим, что удалился. Запрос на получение тега по имени должен быть пустой
        resp = api.get(f'/estates/{estate_id}/tags/{id}', auth_as=user['email'])
        assert not resp.result


def test_delete_tags(api):
    resp = api.delete(f'/estates/1/tags', auth_as='anna@biganto.com')
    assert resp.status_code == 204
    # Проверим, что удалились
    resp = api.get(f'/estates/1/tags', auth_as='anna@biganto.com')
    assert resp.result == []


@pytest.mark.bad_requests
def test_exception(api):
    """
    """
    for user_id, user in USERS.items():
        estate_id = user_id
        tag_id = user_id
        # POST /estates/<id>/tags
        # не существующий estate_id
        body = {'name': 'metro', 'value': 'some_value'}
        resp = api.post(f'/estates/2/tags', body, auth_as=user['email'])
        assert resp.status_code == 404

        # отсутствует ключ name
        body = {'1': 12, 'value': 'some value'}
        resp = api.post(f'/estates/{estate_id}/tags', body, auth_as=user['email'])
        assert resp.status_code == 400

        # Тега с именем some_name не существует
        body = {'name': 'some_name', 'value': 'some value'}
        resp = api.post(f'/estates/{estate_id}/tags', body, auth_as=user['email'])
        assert resp.status_code == 404

        # Отсутствует ключи
        body = {}
        resp = api.post(f'/estates/{estate_id}/tags', body, auth_as=user['email'])
        assert resp.status_code == 400

        # Присутствует лишний ключ
        body = {'name': 'metro', 'value': 'some value', 'some_key': 'some_val'}
        resp = api.post(f'/estates/{estate_id}/tags', body, auth_as=user['email'])
        assert resp.status_code == 400

        # PUT /estates/<id>/tags
        # не существующий estate
        body = {'value': 'some_value'}
        resp = api.put(f'/estates/{estate_id+1}/tags/{tag_id}', body, auth_as=user['email'])
        assert resp.status_code == 404

        # Добавлен дополнительный ключ some_key
        body = {'value_': 'some value', 'some_key': 'some value'}
        resp = api.put(f'/estates/{estate_id}/tags/{tag_id}', body, auth_as=user['email'])
        assert resp.status_code == 400

        # GET /estates/<int:estate_id>/tags'

        # Estate not found.
        resp = api.get(f'/estates/{estate_id+1}/tags', auth_as=user['email'])
        assert resp.status_code == 404

        # format_values не парсится в boolean
        qs = {'format_values': 2}
        resp = api.get(f'/estates/{estate_id}/tags', query_string=qs, auth_as=user['email'])
        assert resp.status_code == 400

        # format_values не парсится в boolean
        qs = {'format_values': 'qw'}
        resp = api.get(f'/estates/{estate_id}/tags', query_string=qs, auth_as=user['email'])
        assert resp.status_code == 400

        # group_tags не "id" или "name"
        qs = {'group_tags': 'some_value'}
        resp = api.get(f'/estates/{estate_id}/tags', query_string=qs, auth_as=user['email'])
        assert resp.status_code == 400

        # group_tags не "id" или "name"
        qs = {'group_tags': 2}
        resp = api.get(f'/estates/{estate_id}/tags', query_string=qs, auth_as=user['email'])
        assert resp.status_code == 400

        # GET /estates/<int:estate_id>/tag_id

        # Estate not found.
        tag_name = 'metro'
        resp = api.get(f'/estates/{estate_id+1}/tags/{tag_id}', auth_as=user['email'])
        assert resp.status_code == 404

        # Tag not found.
        resp = api.get(f'/estates/{estate_id}/tags/{tag_id+10}', query_string=qs, auth_as=user['email'])
        assert resp.status_code == 404

        # GET /estates/<int:estate_id>/tag_name
        # Estate not found.
        resp = api.get(f'/estates/{estate_id+1}/tags/{tag_name}', auth_as=user['email'])
        assert resp.status_code == 404

        # тега с таким именем нет
        resp = api.get(f'/estates/{estate_id}/tags/some_tag_name', auth_as=user['email'],)
        assert resp.status_code == 200
        assert not resp.result

        # DELETE /estates/<int:estate_id>/tags/<int:tag_id>
        # Estate not found.
        resp = api.delete(f'/estates/{estate_id+1}/tags/{tag_id}', auth_as=user['email'])
        assert resp.status_code == 404

        # тега с таким ID нет
        resp = api.delete(f'/estates/{estate_id}/tags/{tag_id+50}', auth_as=user['email'])
        assert resp.status_code == 404

        # DELETE /estates/<int:estate_id>/tags/<name>
        # Estate not found.
        resp = api.delete(f'/estates/{estate_id+1}/tags/{tag_name}', auth_as=user['email'])
        assert resp.status_code == 404

        # тега с таким именем нет
        resp = api.delete(f'/estates/{estate_id}/tags/some_name', auth_as=user['email'],)
        assert resp.status_code == 204
