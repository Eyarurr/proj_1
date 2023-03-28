import pytest
import os
import datetime

from visual import create_app
from visual.core import db
from visual.models import Footage, Tour, TourVideo, Estate, Tag, EstateAsset
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

        db.session.add(Estate(id=1, user_id=1, title='Estate 1'))
        db.session.add(Estate(id=3, user_id=1, title='Estate 3'))

        db.session.commit()


def test_post_assets_bad(api):
    """
    POST /estates/<id>/assets
    """
    set_flow({
        'TOKEN': ['src/1-1.jpg']
    })

    bodies = [
        ('owner@biganto.com', 1, {}),  # Пустое тело
        ('owner@biganto.com', 1, {'url': 'flow@TOKEN/1-1.jpg'}),  # Нет типа
        ('owner@biganto.com', 1, {'type': 'nonexistent', 'url': 'flow@TOKEN/1-1.jpg'}),  # Несуществующий тип
        ('owner@biganto.com', 1, {'type': 'photo'}),  # Нет урла
        ('owner@biganto.com', 1, {'type': 'photo', 'url': 'flow@TOKEN/nonexistent.txt'}),  # Несуществующий файла
        ('owner@biganto.com', 1, {'type': 'tour'}),  # Нет tour_id
        ('owner@biganto.com', 1, {'type': 'tour', 'tour_id': 999999}),  # Нет tour_id
        ('owner@biganto.com', 1, {'type': 'tour_video'}),  # Нет tour_id
        ('owner@biganto.com', 1, {'type': 'tour_video', 'tour_video_id': 999999}),  # Нет tour_id
    ]
    for auth_as, estate_id, body in bodies:
        resp = api.post(f'/estates/{estate_id}/assets', body=body, auth_as=auth_as)
        assert resp.status_code in (400, 403, 404), f'{auth_as} - {estate_id} - {body} - {resp.object}'


def test_post_assets_good(api):
    """
    POST /estates/<id>/assets
    """
    set_flow({
        'TOKEN': ['src/1-1.jpg', 'src/1.mp4', 'src/meta.json'],
    })

    bodies = [
        ('owner@biganto.com', 1, {'type': 'tour', 'tour_id': 1, 'sort': 10, 'title': 'Это тур'}),
        ('owner@biganto.com', 1, {'type': 'tour_video', 'tour_video_id': 1, 'sort': 5, 'title': 'А это видос'}),
        ('owner@biganto.com', 3, {'type': 'other', 'url': 'flow@TOKEN/meta.json'}),
        ('owner@biganto.com', 3, {'type': 'photo', 'url': 'flow@TOKEN/1-1.jpg', 'title': 'Я и моя сраная кошка'}),
        ('owner@biganto.com', 3, {'type': 'plan', 'url': 'flow@TOKEN/1-1.jpg'}),
        ('owner@biganto.com', 3, {'type': 'screenshot', 'url': 'flow@TOKEN/1-1.jpg'}),
        ('owner@biganto.com', 3, {'type': 'video', 'url': 'flow@TOKEN/1.mp4'}),
    ]
    for auth_as, estate_id, body in bodies:
        resp = api.post(f'/estates/{estate_id}/assets', body=body, auth_as=auth_as)
        assert resp.status_code == 200, f'{auth_as} - {estate_id} - {body} - {resp.object}'
        assert resp.result['type'] == body['type']
        assert resp.result['url']
        if body['type'] in EstateAsset.PREVIEW_SIZES:
            assert resp.result['preview_url']
        if 'title' in body:
            assert resp.result['title'] == body['title']
        if body['type'] == 'tour':
            assert resp.result['tour']
            assert resp.result['tour']['title'] == 'Какой-то тур'
            assert resp.result['tour']['hidden'] is False
            assert resp.result['url'] == f'/tour/{body["tour_id"]}/'
        if body['type'] == 'tour_video':
            assert resp.result['tour_video']
            assert resp.result['url'].endswith('some-s3-key.mp4')
        MEMO['assets'][resp.result['id']] = resp.result

    # Проверяем, что залилось
    # resp = api.get(f'/estates/1', auth_as='owner@biganto.com', query_string={'assets': '*'})


def test_get_estates(api):
    resp = api.get(f'/estates/3', auth_as='owner@biganto.com', query_string={'tags': '*', 'assets': '*', 'assets_sort': 'type'})
    assert resp.status_code == 200, f'{resp.object}'
    assert 'assets' in resp.result and len(resp.result['assets']) == 5


def test_put_estate_asset(api):
    resp = api.put(f'/estates/1/assets/1', auth_as='owner@biganto.com', body={'title': 'Тыр пыр', 'sort': -10})
    assert resp.status_code == 200, f'{resp.object}'
    assert resp.result['title'] == 'Тыр пыр'
    assert resp.result['sort'] == -10

    resp = api.put(f'/estates/1/assets/1', auth_as='owner@biganto.com', body={'title': 'Тыр пыр2'})
    assert resp.status_code == 200, f'{resp.object}'
    resp = api.put(f'/estates/1/assets/1', auth_as='owner@biganto.com', body={'sort': 1000})
    assert resp.status_code == 200, f'{resp.object}'


def test_get_estate_assets(api):
    resp = api.get(f'/estates/1/assets', auth_as='owner@biganto.com', query_string={'sort': 'sort'})
    assert resp.status_code == 200, f'{resp.object}'
    assert type(resp.result) is list
    assert len(resp.result) == 2
    assert resp.result[0]['sort'] == 5
    assert resp.result[1]['sort'] == 1000

    resp = api.get(f'/estates/3/assets', auth_as='owner@biganto.com', query_string={'type': 'photo,video', 'sort': '-size'})
    assert resp.status_code == 200, f'{resp.object}'
    assert type(resp.result) is list
    assert len(resp.result) == 2
    assert resp.result[0]['type'] == 'video'
    assert resp.result[1]['type'] == 'photo'


# Чтобы посмотреть на заливаемые в S3 файлы, отключите этот тест
# @pytest.mark.skip
def test_delete_asset_good(api):
    """
    DELETE /estates/<id>/assets/<id>
    """
    for asset_id, asset in MEMO['assets'].items():
        if asset['estate_id'] == 3:
            resp = api.delete(f'/estates/{asset["estate_id"]}/assets/{asset_id}', auth_as='owner@biganto.com')
            assert resp.status_code == 204


def test_delete_assets_good(api):
    """
    DELETE /estates/<id>/assets
    """
    resp = api.delete(f'/estates/1/assets', auth_as='owner@biganto.com')
    assert resp.status_code == 204, f'{resp.object}'

    resp = api.get(f'/estates/1/assets', auth_as='owner@biganto.com')
    assert resp.status_code == 200, f'{resp.object}'
    assert resp.result == []


# Чтобы посмотреть на заливаемые в S3 файлы, отключите этот тест
# @pytest.mark.skip
def test_delete_estate(api):
    resp = api.delete('/estates/3', auth_as='owner@biganto.com')
    assert resp.status_code == 204

    resp = api.get(f'/estates/3', auth_as='owner@biganto.com')
    assert resp.status_code == 404
