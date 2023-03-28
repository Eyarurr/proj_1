"""
"""
import datetime

from visual import create_app
from visual.core import db
from visual.models import User, AuthToken, City, Country, TeamMember, BROffice, BROperator, BROrder, UserProduct, BROrderAsset, Estate
from ..common import set_flow
from .setup import create_users, create_tours

# Сторадж для передачи данных между тестами
MEMO = {
    'users': {},
    'tours': {},
    'orders': {},
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
            {'id': 1, 'email': 'user1@biganto.com', 'name': 'User 1'},
            {'id': 2, 'email': 'user2@biganto.com', 'name': 'User 1'},
            {'id': 10, 'email': 'operator1@biganto.com', 'name': 'Operator 1.1'},
            {'id': 11, 'email': 'operator2@biganto.com', 'name': 'Operator 2.1'},
            {'id': 12, 'email': 'operator3@biganto.com', 'name': 'Operator 2.2'},
            {'id': 50, 'email': 'manager@biganto.com', 'name': 'Manager'},
            {'id': 100, 'email': 'nobody@biganto.com', 'name': 'Manager'},
        ]
        result = {}
        for kwargs in users:
            user = User(email_confirmed=True, **kwargs)
            user.auth_tokens.append(
                AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30), ip='0.0.0.0')
            )
            if kwargs['email'] != 'nobody@biganto.com':
                user.user_products.append(
                    UserProduct(product_id='bladerunner', plan_id=100)
                )
            db.session.add(user)
            result[user.id] = {'id': user.id, 'email': user.email, 'name': user.name}

        db.session.add(Estate(id=1, user_id=1, title='Estate 1'))
        db.session.add(Estate(id=2, user_id=2, title='Estate 1'))

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
            {'status': 'success', 'customer_id': 1, 'office_id': 1, 'operator_id': 10,
             'start': tomorrow('10:30+03:00'),
             'tts': 60, 'coords': [55.71779551101947, 37.633319337082064], 'address': 'Изначально созданный в setup(), success'}
        ]
        for kwargs in orders:
            order = BROrder(**kwargs)
            db.session.add(order)

        db.session.flush()
        assets = [
            {'order_id': 1, 'operator_id': 10, 'type': 'photo', 's3key': 'ASSET1-KEY', 'preview_s3key': 'ASSET1-PREVIEW-KEY'},
            {'order_id': 1, 'operator_id': 10, 'type': 'video', 's3key': 'ASSET2-KEY', 'preview_s3key': 'ASSET2-PREVIEW-KEY'},
            {'order_id': 1, 'operator_id': 10, 'type': 'screenshot', 's3key': 'ASSET3-KEY', 'preview_s3key': 'ASSET3-PREVIEW-KEY'},
            {'order_id': 1, 'operator_id': 10, 'type': 'screenshot', 's3key': 'ASSET4-KEY', 'preview_s3key': 'ASSET4-PREVIEW-KEY'},
        ]
        for kwargs in assets:
            asset = BROrderAsset(**kwargs)
            db.session.add(asset)

        db.session.commit()


def tomorrow(time):
    """
    Возвращает datetime.datetime в завтрашнем дне и с временем, указанным в ISO-формате в параметре `time`
    """
    return datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time.fromisoformat(time))


def today(time):
    """
    Возвращает datetime.datetime в завтрашнем дне и с временем, указанным в ISO-формате в параметре `time`
    """
    return datetime.datetime.combine(datetime.date.today(), datetime.time.fromisoformat(time))


def test_get_free_time_bad(api):
    """
    GET /bladerunner/freetime
    """
    good_body = {
        'city_id': '1',
        'date': (datetime.date.today() + datetime.timedelta(days=1)).isoformat(),
        'coords': '55.71786195596882, 37.62960712132469',
        'tts': '60'
    }

    bodies = [
        ('nobody@biganto.com', good_body),
        ('user1@biganto.com', {}),
        ('user1@biganto.com', {**good_body, **{'city_id': 'nonexistent'}}),
        ('user1@biganto.com', {**good_body, **{'city_id': '5000000'}}),
        ('user1@biganto.com', {**good_body, **{'date': (datetime.date.today() - datetime.timedelta(days=1)).isoformat()}}),
        ('user1@biganto.com', {**good_body, **{'date': (datetime.date.today()).isoformat()}}),
        ('user1@biganto.com', {**good_body, **{'tts': 0}}),
        ('user1@biganto.com', {**good_body, **{'tts': 'asdsada'}}),
        ('user1@biganto.com', {**good_body, **{'tts': '-1'}}),
    ]
    for auth_as, body in bodies:
        resp = api.get('/bladerunner/freetime', query_string=body, auth_as=auth_as)
        assert resp.status_code in (400, 403, 404), f'{auth_as} - {body} - {resp.object}'


def test_get_free_time_good(api):
    """
    GET /bladerunner/freetime
        ?city_id=1
        ?date=TOMORROW
        ?coords=1,0
        ?tts=60
    """

    qs = {
        'city_id': '1',
        'date': (datetime.date.today() + datetime.timedelta(days=1)).isoformat(),
        # Рядом с Дубининской
        'coords': '55.71786195596882, 37.62960712132469',
        'tts': '60'
    }
    resp = api.get('/bladerunner/freetime', query_string=qs, auth_as='user1@biganto.com')
    assert resp.status_code == 200, f'{qs} - {resp.object}'
    assert resp.result


def test_post_order_bad(api):
    """
    POST /bladerunner/orders
    """
    # (auth_as, body)
    good_body = {
        'city_id': '1',
        'start': tomorrow('12:00+03:00').isoformat(),
        'tts': 60,
        'coords': '55.71786195596882, 37.62960712132469',
        'address': 'okay',
        'contacts': [{'phone': '+71234567890', 'name': 'ok'}]
    }
    bodies = [
        ('nobody@biganto.com', good_body),
        ('user1@biganto.com', {}),
        ('user1@biganto.com', {**good_body, **{'start': (datetime.datetime.now() - datetime.timedelta(seconds=10)).isoformat()}}),
        ('user1@biganto.com', {**good_body, **{'start': today('15:00:00+03:00').isoformat()}}),
        ('user1@biganto.com', {**good_body, **{'tts': 0}}),
        ('user1@biganto.com', {**good_body, **{'tts': 'asdsada'}}),
        ('user1@biganto.com', {**good_body, **{'tts': '-1'}}),
        ('user1@biganto.com', {**good_body, **{'estate_id': 100000}}),  # Несущетвующий estate
        ('user1@biganto.com', {**good_body, **{'estate_id': 2}}),  # Чужой estate
    ]
    for auth_as, body in bodies:
        resp = api.post('/bladerunner/orders', body=body, auth_as=auth_as)
        assert resp.status_code in (400, 403, 404), f'{auth_as} - {body} - {resp.object}'


def test_post_order_good(api):
    """
    POST /bladerunner/orders
        ?city_id=1
        ?start=TODAY + 9:16+3
        ?tts=60
        ?coords: '55.71786195596882, 37.62960712132469',
    """

    body = {
        'city_id': '1',
        'start': tomorrow('14:00+03:00'),
        'tts': '60',
        # Рядом с Дубининской
        'coords': '55.71786195596882, 37.62960712132469',
        'address': 'Дубининская 84',
        'contacts': [{'phone': '2128506', 'name': 'Космос Юрьевич Холмогоров'}, {'name': 'Хуй Петрович Дзержинский'}],
        'customer_comment': 'Оператор не должен быть рыжим',
        'estate_id': 1
    }
    resp = api.post('/bladerunner/orders', body=body, auth_as='user1@biganto.com')
    assert resp.status_code == 200, f'{body} - {resp.object}'
    assert resp.result
    MEMO['orders'][resp.result['id']] = resp.result


def test_put_order_bad(api):
    """
    PUT /bladerunner/orders/<id>
    """
    # auth_as, order_index, body
    bodies = [
        ('user2@biganto.com', 0, {'contacts': [{'phone': '1', 'name': 'Кокос Кокосыч'}], 'customer_comment': 'AAA'}),
        ('user1@biganto.com', 0, {'status': 'nonexistent'}),
        ('user1@biganto.com', 0, {'status': 'progress.shooting'}),
        ('user1@biganto.com', 0, {'estate_id': 10000000}),
        ('user1@biganto.com', 0, {'estate_id': 2}),
    ]
    for auth_as, order_index, body in bodies:
        order_id = list(MEMO["orders"].values())[order_index]['id']
        resp = api.put(f'/bladerunner/orders/{order_id}', body=body, auth_as=auth_as)
        assert resp.status_code in (400, 403, 404), f'{auth_as} - {order_id} - {body} - {resp.object}'


def test_put_order_good(api):
    """
    PUT /bladerunner/orders/<id>
    """
    # auth_as, order_index, body
    bodies = [
        ('user1@biganto.com', 0, {'contacts': [{'phone': '1', 'name': 'Кокос Кокосыч'}], 'customer_comment': 'AAA'}),
        ('user1@biganto.com', 0, {'status': 'reschedule.customer'}),
        ('user1@biganto.com', 0, {'status': 'canceled'}),
    ]
    for auth_as, order_index, body in bodies:
        order_id = list(MEMO["orders"].values())[order_index]['id']
        resp = api.put(f'/bladerunner/orders/{order_id}', body=body, auth_as=auth_as)
        assert resp.status_code == 200, f'{auth_as} - {order_id} - {body} - {resp.object}'

        if 'contacts' in body:
            assert resp.result['contacts'] == body['contacts']
        if 'customer_comment' in body:
            assert resp.result['customer_comment'] == body['customer_comment']
        if 'status' in body:
            assert resp.result['status'] == body['status']

        MEMO['orders'][order_id] = resp.result


def test_get_orders(api):
    """
    GET /bladerunner/orders
    """
    qs = {
        'status': 'scheduled,progress.*',
        'total': 1
    }
    resp = api.get('/bladerunner/orders', query_string=qs, auth_as='user1@biganto.com')
    assert resp.status_code == 200, f'{resp.object}'

    qs = {
        'assets': '*',
        'total': 1
    }
    resp = api.get('/bladerunner/orders', query_string=qs, auth_as='user1@biganto.com')
    assert resp.status_code == 200, f'{resp.object}'
    for order in resp.result:
        if order['id'] == 1:
            assert len(order['assets']) == 4

    qs = {
        'assets': 'photo,video',
        'total': 1
    }
    resp = api.get('/bladerunner/orders', query_string=qs, auth_as='user1@biganto.com')
    assert resp.status_code == 200, f'{resp.object}'
    for order in resp.result:
        if order['id'] == 1:
            assert len(order['assets']) == 2
            for asset in order['assets']:
                assert asset['type'] in ('photo', 'video')


def test_get_order_bad(api):
    """
    GET /bladerunner/orders/<id>
    """
    resp = api.get(f'/bladerunner/orders/1', auth_as='user2@biganto.com')
    assert resp.status_code in (403, 404)


def test_get_order_good(api):
    """
    GET /bladerunner/orders/<id>
    """
    resp = api.get(f'/bladerunner/orders/1', auth_as='user1@biganto.com')
    assert resp.status_code == 200
    assert resp.result['id'] == 1


def test_get_order_assets_good(api):
    """
    GET /bladerunner/orders/<id>/assets
    """
    resp = api.get(f'/bladerunner/orders/1/assets', query_string={}, auth_as='user1@biganto.com')
    assert resp.status_code == 200


def test_get_cities(api):
    """
    GET /bladerunner/cities
    """
    qs = {'country_id': 'TT'}
    resp = api.get('/bladerunner/cities', query_string=qs, auth_as='user1@biganto.com')
