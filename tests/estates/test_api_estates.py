import pytest
import os
import datetime

from visual import create_app
from visual.core import db
from visual.models import Footage, Tour, TourVideo, User, AuthToken, Tag, EstateAsset
from tests.common import set_flow, create_users

# Сторадж для передачи данных между тестами
MEMO = {
    'tours': {},
    'estates': {},
    'assets': {},
}


def create_tags(user_id):
    """
    Создаёт юзеру `user_id` теги:
        description
        price
        area
        metro
    """
    tags = [
        Tag(user_id=user_id, name='description'),
        Tag(user_id=user_id, name='price', label='Цена', suffix=' руб.'),
        Tag(user_id=user_id, name='area', label='Площадь', prefix='примерно ', suffix=' м2'),
        Tag(user_id=user_id, name='metro', prefix='м. ', display_dict={'1': 'Пятницкая', '2': 'Новокузнецкая'}),
        Tag(user_id=user_id, name='ghosts', label='Есть привидения')
    ]
    db.session.add_all(tags)


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
        Tour(id=1, footage=footage1, title='Какой-то тур', user_id=1),
        Tour(id=2, footage=footage1, title='Ещё какой-то тур', user_id=1),
        Tour(id=3, footage=footage2, title='Tour 3 (admin)', user_id=10),
    ]
    for tour in tours:
        db.session.add(tour)

    db.session.add(TourVideo(
        user_id=1, video_s3_key='some-s3-key.mp4', preview_s3_key='some-s3-key-preview.jpg',
        width=333, height=444, size=555, duration=666, tour=tours[0]
    ))


def setup_module():
    """
    Создаёт стандартных юзеров через create_users()
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()

        create_users({
            1: dict(email='owner@biganto.com', name='Owner'),
            2: dict(email='client@biganto.com', name='Client'),
            10: dict(email='cocksucker@biganto.com', name='Левый хер')
        })

        db.session.flush()
        create_tags(1)
        create_tours()

        db.session.commit()


@pytest.mark.bad_requests
def test_post_estates_bad(api):
    """
    POST /my/estates
    """
    # [(auth_as, body), ...]
    bodies = [
        ('owner@biganto.com', 'Я сделан из мяса'),  # Тело запроса — не объект
        ('owner@biganto.com', {}),                  # Пустое тело запроса
        ('owner@biganto.com', {'foo': 'bar'}),      # Отсутствует title
        ('owner@biganto.com', {'title': None}),     # Плохой тип имени
        ('owner@biganto.com', {'title': ''}),       # Пустое имя
        ('owner@biganto.com', {'title': '     '}),  # Пустое имя
        ('owner@biganto.com', {'title': 'Valid', 'tags': [{'value': '300'}]}),  # Отсутствует имя тега
        ('owner@biganto.com', {'title': 'Valid', 'tags': [{'name': ''}]}),  # Пустое имя тега
        ('owner@biganto.com', {'title': 'Valid', 'tags': [{'name': '   '}]}),  # Имя тега пробельное
        ('owner@biganto.com', {'title': 'Valid', 'tags': [{'name': 'nonexistent', 'value': 'yes'}]}),  # Несуществующий тег
    ]
    for auth_as, body in bodies:
        resp = api.post(f'/my/estates', body, auth_as=auth_as)
        assert resp.status_code == 400, f'{auth_as} - {body} - {resp.object}'


def test_post_estates(api):
    # [(auth_as, body), ...]
    bodies = [
        ('owner@biganto.com', {'title': 'Дом 1', 'remote_id': '555-777'}),
        ('owner@biganto.com', {'title': '  Дом 2  '}),
        ('owner@biganto.com', {
            'title': 'Дом 3',
            'tags': [
                {'name': 'description', 'value': 'Описание объекта'},
                {'name': 'price', 'value': '300000'},
                {'name': 'area', 'value': '98'},
                {'name': 'metro', 'value': '1'},
                {'name': 'metro', 'value': '2'},
                {'name': 'ghosts'},
            ]
        }),
    ]
    for auth_as, body in bodies:
        resp = api.post(f'/my/estates', body, auth_as=auth_as)
        assert resp.status_code == 200, f'{auth_as} - {body} - {resp.object}'
        assert resp.result
        assert 'id' in resp.result
        assert resp.result['title'] == body['title'].strip()
        if 'remote_id' in body:
            assert 'remote_id' in resp.result and resp.result['remote_id'] == body['remote_id']
        if 'tags' in body:
            assert 'tags' in resp.result
            assert len(resp.result['tags']) == len(body['tags'])
            assert set([tag['name'] for tag in resp.result['tags']]) == set([tag['name'] for tag in body['tags']])
            assert set([tag.get('value') for tag in resp.result['tags']]) == set([tag.get('value') for tag in body['tags']])
        MEMO['estates'][resp.result['id']] = resp.result


def test_put_estates(api):
    # [(auth_as, estate_id, body), ...]
    bodies = [
        ('owner@biganto.com', 1, {'title': ' Дом #1 ', 'remote_id': '777-555'}),
        ('owner@biganto.com', 2, {
            'tags': [
                dict(name='price', value=300),
                dict(name='area', value=30),
            ]
        }),
        ('owner@biganto.com', 2, {
            'tags': [
                dict(id=9, value=40),
                dict(name='area', value='40'),
                dict(name='ghosts'),
            ]
        }),
    ]
    for auth_as, estate_id, body in bodies:
        resp = api.put(f'/estates/{estate_id}', body, auth_as=auth_as)
        assert resp.status_code == 200, f'{auth_as} - {body} - {resp.object}'
        assert resp.result
        assert 'id' in resp.result
        if 'title' in body:
            assert resp.result['title'] == body['title'].strip()
        MEMO['estates'][resp.result['id']] = resp.result


def test_get_estates(api):
    resp = api.get(f'/my/estates', auth_as='owner@biganto.com')
    assert resp.status_code == 200
    assert type(resp.result) is list
    for estate in resp.result:
        assert estate['title']
        if estate['id'] == 1:
            assert estate['remote_id'] == '777-555'
        assert estate.get('tags', []) == []
        assert estate.get('assets', []) == []

    resp = api.get(f'/my/estates', auth_as='owner@biganto.com', query_string={'tags': '*'})
    assert resp.status_code == 200, f'{resp.object}'
    for estate in resp.result:
        if estate['id'] == 3:
            assert 'tags' in estate and len(estate['tags']) == 6

    resp = api.get(f'/my/estates', auth_as='owner@biganto.com', query_string={'tags': 'metro,price', 'sort': 'title'})
    assert resp.status_code == 200, f'{resp.object}'
    assert resp.result[0]['title'] == 'Дом #1'
    assert resp.result[1]['title'] == 'Дом 2'
    assert resp.result[2]['title'] == 'Дом 3'
    for estate in resp.result:
        if estate.get('tags'):
            assert type(estate['tags']) is list
            assert set([tag['name'] for tag in estate['tags']]) - {'metro', 'price'} == set()

    resp = api.get(f'/my/estates', auth_as='owner@biganto.com', query_string={'tags': '*', 'group_tags': 'name', 'format_values': '1'})
    assert resp.status_code == 200, f'{resp.object}'
    for estate in resp.result:
        if 'tags' in estate:
            assert type(estate['tags']) is dict
        if estate['id'] == 2:
            assert sorted(list(estate['tags'].keys())) == sorted(['price', 'area', 'ghosts'])
            assert len(estate['tags']['area']) == 2
            assert estate['tags']['price'][0]['value'] == '300 руб.'
        if estate['id'] == 3:
            assert set(list(estate['tags'].keys())) == {'description', 'price', 'area', 'metro', 'ghosts'}
            tag = estate['tags']['price'][0]
            assert tag['value'] == '300000 руб.'


def test_get_estate(api):
    resp = api.get(f'/estates/3', auth_as='owner@biganto.com', query_string={'tags': '*'})
    assert resp.status_code == 200, f'{resp.object}'
    assert type(resp.result) is dict
    assert type(resp.result['tags']) is list
    assert 'tags' in resp.result and len(resp.result['tags']) == 6

    resp = api.get(f'/estates/3', auth_as='owner@biganto.com', query_string={'tags': 'metro,price'})
    assert resp.status_code == 200, f'{resp.object}'
    assert set([tag['name'] for tag in resp.result['tags']]) == {'metro', 'price'}

    resp = api.get(f'/estates/3', auth_as='owner@biganto.com', query_string={'tags': '*', 'group_tags': 'name', 'format_values': '1'})
    assert resp.status_code == 200, f'{resp.object}'
    assert type(resp.result['tags']) is dict
    assert set(list(resp.result['tags'].keys())) == {'description', 'price', 'area', 'metro', 'ghosts'}
    assert resp.result['tags']['price'][0]['value'] == '300000 руб.'


def test_delete_estate(api):
    resp = api.delete('/estates/3', auth_as='owner@biganto.com')
    assert resp.status_code == 204

    resp = api.get(f'/estates/3', auth_as='owner@biganto.com')
    assert resp.status_code == 404
