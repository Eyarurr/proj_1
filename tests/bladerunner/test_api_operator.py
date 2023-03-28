"""
"""
import pytest
import datetime

from visual import create_app
from visual.core import db
from visual.models import User, AuthToken, City, Country, TeamMember, BROffice, BROperator, BROrder, UserProduct, Tour, Footage, TourVideo, BROrderAsset
from ..common import set_flow
from .setup import create_users, create_tours

# Сторадж для передачи данных между тестами
MEMO = {
    'users': {},
    'tours': {},
    'estates': {},
    'assets': {}
}


def setup_module():
    """
    Создаёт стандартных юзеров через create_users()
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()

        country = Country(id='TT', name_ru='Татарстан')
        db.session.add(country)

        city = City(id=1, country_id='TT', name_ru='Казань', name_en='Kazan')
        db.session.add(city)

        users = [
            {'id': 1, 'email': 'user@biganto.com', 'name': 'User 1'},
            {'id': 10, 'email': 'operator1@biganto.com', 'name': 'Operator 1.1'},
            {'id': 11, 'email': 'operator2@biganto.com', 'name': 'Operator 2.1'},
            {'id': 12, 'email': 'operator3@biganto.com', 'name': 'Operator 2.2'},
            {'id': 50, 'email': 'manager@biganto.com', 'name': 'Manager'},
        ]
        result = {}
        for kwargs in users:
            user = User(email_confirmed=True, **kwargs)
            user.auth_tokens.append(
                AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30), ip='0.0.0.0')
            )
            user.user_products.append(
                UserProduct(product_id='bladerunner', plan_id=100)
            )
            if kwargs['email'].startswith('operator'):
                user.team_member = TeamMember(roles=['br.operator'])
            db.session.add(user)
            result[user.id] = {'id': user.id, 'email': user.email, 'name': user.name}

        offices = [
            # Новокузнецкая
            {'id': 1, 'manager_id': 50, 'active': True, 'city_id': 1, 'coords': [55.74237415946115, 37.62939569670399], 'title': 'Office 0:0', 'work_start': '9:00', 'work_end': '20:00'},
        ]
        for kwargs in offices:
            office = BROffice(**kwargs)
            db.session.add(office)

        db.session.flush()

        operators = [
            {'user_id': 10, 'office_id': 1, 'active': True, 'work_start': '9:00', 'work_end': '18:00'},
            {'user_id': 11, 'office_id': 1, 'active': True, 'work_start': '18:00', 'work_end': '21:00'}
        ]
        for kwargs in operators:
            operator = BROperator(**kwargs)
            db.session.add(operator)

        orders = [
            {'status': 'scheduled', 'customer_id': 1, 'office_id': 1, 'operator_id': 10, 'start': '2023-03-23T10:30', 'tts': 60, 'coords': [55.71779551101947, 37.633319337082064], 'address': 'Дубининская, 84'},
            {'status': 'success', 'customer_id': 1, 'office_id': 1, 'operator_id': 10, 'start': '2023-01-08T10:30', 'tts': 60, 'coords': [55.71779551101947, 37.633319337082064], 'address': 'Дубининская, 84'},
            {'status': 'scheduled', 'customer_id': 1, 'office_id': 1, 'operator_id': 11, 'start': '2023-03-23T12:00', 'tts': 60, 'coords': [55.71779551101947, 37.633319337082064], 'address': 'Дубининская, 84'}
        ]
        for kwargs in orders:
            order = BROrder(**kwargs)
            db.session.add(order)

        footage = Footage(user_id=10, type='virtual', _status='published', tours=[Tour(user_id=10, title='Какой-то тур')])
        db.session.add(footage)

        db.session.add(TourVideo(
            user_id=10, video_s3_key='some-s3-key.mp4', preview_s3_key='some-s3-key-preview.jpg',
            width=333, height=444, size=555, duration=666, tour=footage.tours[0]
        ))

        db.session.commit()


def test_put_order_bad(api):
    """
    PUT /bladerunner/operator/orders/<id>
        ?status
        ?operator_comment
    """
    bodies = [
        ('operator1@biganto.com', 1, {'status': 'nonexisting'}),
        ('operator1@biganto.com', 3, {'status': 'progress.enroute'}),
        ('operator1@biganto.com', 1, {'status': 'progress.processing'}),
        ('operator1@biganto.com', 1, {'status': 'canceled'}),
        ('operator1@biganto.com', 1, {'start': '2025-01-01T09:00:00+03:00'}),
    ]
    for auth_as, order_id, body in bodies:
        resp = api.put(f'/bladerunner/operator/orders/{order_id}', body=body, auth_as=auth_as)
        assert resp.status_code in (400, 403, 404), f'{auth_as} - {order_id} - {body} - {resp.object}'


def test_put_order_good(api):
    """
    PUT /bladerunner/operator/orders/<id>
        ?status
        ?operator_comment
    """
    bodies = [
        ('operator1@biganto.com', 1, {'status': 'progress.enroute'}),
        ('operator1@biganto.com', 1, {'status': 'progress.shooting'}),
        ('operator1@biganto.com', 1, {'operator_comment': 'Алга, Кыргызстан!'}),
        ('operator1@biganto.com', 1, {'status': 'progress.shoot_complete', 'operator_comment': 'Вперёд, Дордой, мы с тобой!'}),
    ]
    for auth_as, order_id, body in bodies:
        msg = f'{auth_as} - {order_id} - {body}'
        resp = api.put(f'/bladerunner/operator/orders/{order_id}', body=body, auth_as=auth_as)
        assert resp.status_code == 200, msg
        if 'status' in body:
            assert resp.result['status'] == body['status']
        if 'operator_comment' in body:
            assert resp.result['operator_comment'] == body['operator_comment'], msg


def test_post_checkin(api):
    """
    POST /bladerunner/operator/checkin
    """
    body = {
        'coords': [1, 2],
        'address': 'In the middle of nowhere'
    }
    resp = api.post(f'/bladerunner/operator/checkin', body=body, auth_as='operator1@biganto.com')
    assert resp.status_code == 200
    assert resp.result['status'] == 'smoking'


def test_get_orders(api):
    """
    GET /bladerunner/operator/orders
    """
    resp = api.get(f'/bladerunner/operator/orders', query_string={}, auth_as='operator1@biganto.com')
    assert resp.status_code == 200, f'{resp.object}'

    resp = api.get(f'/bladerunner/operator/orders', query_string={'status': 'progress.*'}, auth_as='operator1@biganto.com')
    assert resp.status_code == 200, f'{resp.object}'


def test_post_assets_bad(api):
    """
    POST /bladerunner/operator/orders/<id>/assets
    """
    set_flow({
        'TOKEN': ['src/1-1.jpg']
    })

    bodies = [
        ('operator1@biganto.com', 1, {}),  # Пустое тело
        ('operator1@biganto.com', 3, {'type': 'photo', 'url': 'flow@TOKEN/1-1.jpg'}),  # Не мой заказ
        ('operator1@biganto.com', 1, {'url': 'flow@TOKEN/1-1.jpg'}),  # Нет типа
        ('operator1@biganto.com', 1, {'type': 'nonexistent', 'url': 'flow@TOKEN/1-1.jpg'}),  # Несуществующий тип
        ('operator1@biganto.com', 1, {'type': 'photo'}),  # Нет урла
        ('operator1@biganto.com', 1, {'type': 'photo', 'url': 'flow@TOKEN/nonexistent.txt'}),  # Несуществующий файла
        ('operator1@biganto.com', 1, {'type': 'tour'}),  # Нет tour_id
        ('operator1@biganto.com', 1, {'type': 'tour', 'tour_id': 999999}),  # Нет tour_id
        ('operator1@biganto.com', 1, {'type': 'tour_video'}),  # Нет tour_id
        ('operator1@biganto.com', 1, {'type': 'tour_video', 'tour_video_id': 999999}),  # Нет tour_id
    ]
    for auth_as, order_id, body in bodies:
        resp = api.post(f'/bladerunner/operator/orders/{order_id}/assets', body=body, auth_as=auth_as)
        assert resp.status_code in (400, 403, 404), f'{auth_as} - {order_id} - {body} - {resp.object}'


def test_post_assets_good(api):
    """
    POST /bladerunner/operator/orders/<id>/assets
    """
    set_flow({
        'TOKEN': ['src/1-1.jpg', 'src/1.mp4', 'src/meta.json'],
    })

    bodies = [
        ('operator1@biganto.com', 1, {'type': 'tour', 'tour_id': 1, 'product_meta': {'foo': 'bar'}}),
        ('operator1@biganto.com', 1, {'type': 'tour_video', 'tour_video_id': 1}),
        ('operator1@biganto.com', 1, {'type': 'photo', 'url': 'flow@TOKEN/1-1.jpg', 'title': 'Я и моя сраная кошка'}),
        ('operator1@biganto.com', 1, {'type': 'plan', 'url': 'flow@TOKEN/1-1.jpg'}),
        ('operator1@biganto.com', 1, {'type': 'screenshot', 'url': 'flow@TOKEN/1-1.jpg'}),
        ('operator1@biganto.com', 1, {'type': 'video', 'url': 'flow@TOKEN/1.mp4'}),
        ('operator1@biganto.com', 1, {'type': 'other', 'url': 'flow@TOKEN/meta.json'}),
    ]
    for auth_as, order_id, body in bodies:
        resp = api.post(f'/bladerunner/operator/orders/{order_id}/assets', body=body, auth_as=auth_as)
        assert resp.status_code == 200, f'{auth_as} - {order_id} - {body} - {resp.object}'
        assert resp.result['type'] == body['type']
        assert resp.result['url']
        if body['type'] in BROrderAsset.PREVIEW_SIZES:
            assert resp.result['preview_url']
        if 'title' in body:
            assert resp.result['title'] == body['title']
        if 'product_meta' in body:
            assert resp.result['product_meta'] == body['product_meta']
        if body['type'] == 'tour':
            assert resp.result['tour']
            assert resp.result['tour']['title'] == 'Какой-то тур'
            assert resp.result['tour']['hidden'] is False
            assert resp.result['url'] == f'/tour/{body["tour_id"]}/'
        if body['type'] == 'tour_video':
            assert resp.result['tour_video']
            assert resp.result['url'].endswith('some-s3-key.mp4')
        MEMO['assets'][resp.result['id']] = resp.result

    # Смотрим, появились ли ассеты в списке всех моих заказов, если попросить
    resp = api.get(f'/bladerunner/operator/orders', query_string={'assets': '*'}, auth_as='operator1@biganto.com')
    assert resp.status_code == 200, f'{resp.object}'
    for order in resp.result:
        if order['id'] == 1:
            assert len(order['assets']) == len(bodies)


def test_get_order_bad(api):
    """
    GET /bladerunner/operator/orders/<id>
    """
    resp = api.get(f'/bladerunner/operator/orders/3', auth_as='operator1@biganto.com')
    assert resp.status_code in (403, 404)


def test_get_order_good(api):
    """
    GET /bladerunner/operator/orders/<id>
    """
    resp = api.get(f'/bladerunner/operator/orders/1', auth_as='operator1@biganto.com')
    assert resp.status_code == 200
    assert resp.result['id'] == 1
    memo_list = list(MEMO['assets'].values())
    assert len(resp.result['assets']) == len(memo_list)
    assert resp.result['assets'][0]['type'] == memo_list[-1]['type']
    assert resp.result['assets'][1]['type'] == memo_list[-2]['type']
    assert resp.result['cnt_assets']
    assert resp.result['cnt_assets']['photo'] == 1
    assert resp.result['cnt_assets']['tour'] == 1
    assert resp.result['cnt_assets']['tour_video'] == 1
    assert resp.result['cnt_assets']['video'] == 1
    assert resp.result['cnt_assets']['screenshot'] == 1
    assert resp.result['cnt_assets']['plan'] == 1


def test_get_order_assets_bad(api):
    """
    GET /bladerunner/operator/orders/<id>/assets
    """
    resp = api.get(f'/bladerunner/operator/orders/3/assets', auth_as='operator1@biganto.com')
    assert resp.status_code in (403, 404)


def test_get_order_assets_good(api):
    """
    GET /bladerunner/operator/orders/<id>/assets
    """
    memo_list = list(MEMO['assets'].values())

    resp = api.get(f'/bladerunner/operator/orders/1/assets', query_string={}, auth_as='operator1@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == len(memo_list)
    assert resp.result[0]['type'] == memo_list[-1]['type']
    assert resp.result[1]['type'] == memo_list[-2]['type']

    resp = api.get(f'/bladerunner/operator/orders/1/assets', query_string={'sort': 'created'}, auth_as='operator1@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == len(MEMO['assets'])
    assert resp.result[0]['type'] == memo_list[0]['type']
    assert resp.result[1]['type'] == memo_list[1]['type']

    resp = api.get(f'/bladerunner/operator/orders/1/assets', query_string={'type': 'tour'}, auth_as='operator1@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == 1
    assert resp.result[0]['type'] == 'tour'

    resp = api.get(f'/bladerunner/operator/orders/1/assets', query_string={'type': 'tour,plan'}, auth_as='operator1@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == 2
    assert resp.result[0]['type'] == 'plan'
    assert resp.result[1]['type'] == 'tour'


# Чтобы посмотреть на заливаемые в S3 файлы, отключите этот тест
# @pytest.mark.skip
def test_delete_asset_good(api):
    """
    DELETE /bladerunner/operator/orders/<id>/assets/<id>
    """
    for asset_id, asset in MEMO['assets'].items():
        resp = api.delete(f'/bladerunner/operator/orders/{asset["order_id"]}/assets/{asset_id}', auth_as='operator1@biganto.com')
        assert resp.status_code == 204
