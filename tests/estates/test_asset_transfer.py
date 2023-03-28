import time
import requests

from visual import create_app
from visual.core import db
from visual.models import Footage, Tour, TourVideo, Country, City, BROffice, BROrder, BROrderAsset, Estate
from ..common import create_users, create_s3_objects


def setup_module():
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()

        create_s3_objects(app, {
            'testing/br-asset-photo.jpg': ('1-1.jpg', 'image/jpeg'),
            'testing/br-asset-photo-preview.jpg': ('1-1.jpg', 'image/jpeg'),
            'testing/br-asset-video.mp4': ('1.mp4', 'video/mp4'),
            'testing/br-asset-video-preview.jpg': ('1-1.jpg', 'image/jpg')
        })

        create_users({
            1: dict(email='customer@biganto.com'),
            10: dict(email='manager@biganto.com'),
            11: dict(email='operator@biganto.com')
        })

        footage = Footage(type='real', _status='published', user_id=1)
        tour = Tour(id=1, footage=footage, title='Tour 1', user_id=1)
        db.session.add(footage)
        db.session.add(tour)

        tour_video = TourVideo(
            id=1, user_id=1, tour_id=1,
            video_s3_key='testing/tourvideo',
            preview_s3_key='testing/tourvideo-preview',
            width=111, height=222, size=333, duration=444
        )
        db.session.add(tour_video)

        # Город, офис, заказ и его ассеты
        db.session.add(Country(id='US', name_en='City Nowhere'))
        db.session.add(City(id=1, country_id='US', name_en='City Nowhere'))
        db.session.add(BROffice(id=1, city_id=1, manager_id=10, coords=[0, 0], title='Office 1', work_start='0:0:0', work_end='23:59:59'))

        order = BROrder(id=1, office_id=1, customer_id=1, status='success', coords=[0, 0])
        db.session.add(order)

        order.assets.append(BROrderAsset(id=1, operator_id=11, type='tour', tour_id=1))
        order.assets.append(BROrderAsset(id=2, operator_id=11, type='tour_video', tour_video_id=1))
        order.assets.append(BROrderAsset(id=3, operator_id=11, type='photo', s3key='testing/br-asset-photo.jpg', preview_s3key='testing/br-asset-photo-preview.jpg'))
        order.assets.append(BROrderAsset(id=4, operator_id=11, type='video', s3key='testing/br-asset-video.mp4', preview_s3key='testing/br-asset-video-preview.jpg'))

        # Эстейт
        estate = Estate(user_id=1, title='Estate 1')
        db.session.add(estate)

        db.session.commit()


# @pytest.mark.skip
def test_from_asset(api):
    """POST /estates/<id>/assets/from-br-asset"""
    # Во всех запросах используется ?force_synchronous, так как тестироование асинхронных методов - та ещё ебала.
    # Если надо потестить асинхронщину, то нужно убрать параметр отсюда и смотреть руками в базу.
    # в visual/jobs/api.py читать config.test.py, а не config.local.py
    qs = {'force_synchronous': 1}
    debug = False

    resp = api.post('/estates/1/assets/from-br-asset/1', auth_as='customer@biganto.com', query_string=qs, _debug=debug)
    assert resp.status_code == 200
    assert resp.result['type'] == 'tour'
    assert resp.result['url']
    assert resp.result['tour_id'] == 1

    resp = api.post('/estates/1/assets/from-br-asset/2', auth_as='customer@biganto.com', query_string=qs, _debug=debug)
    assert resp.status_code == 200
    resp = api.post('/estates/1/assets/from-br-asset/3', auth_as='customer@biganto.com', query_string=qs, _debug=debug)
    assert resp.status_code == 200
    resp = api.post('/estates/1/assets/from-br-asset/4', auth_as='customer@biganto.com', query_string=qs, _debug=debug)
    assert resp.status_code == 200
    resp = api.post('/estates/1/assets/from-br-asset/1', auth_as='customer@biganto.com', query_string=qs, _debug=debug)
    assert resp.status_code == 200
    assert resp.warnings

    resp = api.post('/estates/1/assets/from-br-asset/1', auth_as='customer@biganto.com', query_string={**qs, **{'ignore_existing': 1}}, _debug=debug)
    assert resp.status_code == 200
    assert not resp.warnings

    # Смотрим, что загрузилось
    if 'force_synchronous' not in qs:
        print('\nЖдём 15 секунд, чтобы отработали фоновые задачи')
        time.sleep(15)

    resp = api.get('/estates/1', auth_as='customer@biganto.com', query_string={'assets': '*', 'assets_sort': 'created'})
    assert resp.result['cnt_assets'] == {'tour': 2, 'tour_video': 1, 'photo': 1, 'video': 1}
    assert sorted([ass['type'] for ass in resp.result['assets']]) == sorted(['tour', 'tour_video', 'photo', 'video', 'tour'])
    # И проверяем доступность файлов в S3
    for ass in resp.result['assets']:
        if ass['type'] in ('photo', 'screenshot', 'plan', 'video'):
            r = requests.get(ass['url'])
            assert r.status_code == 200, ass['url']
            r = requests.get(ass['preview_url'])
            assert r.status_code == 200, ass['url']

    # Почистим за собой S3
    resp = api.delete('/estates/1/assets', auth_as='customer@biganto.com')
    assert resp.status_code == 204


# @pytest.mark.skip
def test_from_order(api):
    """POST /estates/<id>/assets/from-br-asset"""
    # Во всех запросах используется ?force_synchronous, так как тестироование асинхронных методов - та ещё ебала.
    # Если надо потестить асинхронщину, то нужно убрать параметр отсюда и смотреть руками в базу. Не забудьте
    # в visual/jobs/api.py читать config.test.py, а не config.local.py
    qs = {'force_synchronous': 1}
    debug = False

    # Воткнём один ассет отдельно
    resp = api.post('/estates/1/assets/from-br-asset/1', auth_as='customer@biganto.com', query_string=qs)
    assert resp.status_code == 200

    # Всосём все, 1-й должен пропуститься
    resp = api.post('/estates/1/assets/from-br-order/1', auth_as='customer@biganto.com', query_string=qs, _debug=debug)
    assert resp.status_code == 200

    # Должны загрузиться все ассеты по разу
    resp = api.get('/estates/1/assets', auth_as='customer@biganto.com', query_string={'sort': 'created'}, _debug=debug)
    assert len(resp.result) == 4
    assert set([ass['type'] for ass in resp.result]) == {'tour', 'tour_video', 'photo', 'video'}

    # Добавляем типы tour, tour_video принудительно
    resp = api.post(
        '/estates/1/assets/from-br-order/1', auth_as='customer@biganto.com',
        query_string={**qs, **{'type': 'tour,tour_video', 'ignore_existing': 1}}, _debug=debug
    )
    assert resp.status_code == 200

    # Смотрим, что загрузилось
    if 'force_synchronous' not in qs:
        print('\nЖдём 15 секунд, чтобы отработали фоновые задачи')
        time.sleep(15)

    resp = api.get('/estates/1', auth_as='customer@biganto.com', query_string={'assets': '*', 'assets_sort': 'created'}, _debug=debug)
    assert resp.result['cnt_assets'] == {'tour': 2, 'tour_video': 2, 'photo': 1, 'video': 1}
    assert len(resp.result['assets']) == 6

    # Почистим за собой S3
    resp = api.delete('/estates/1/assets', auth_as='customer@biganto.com')
    assert resp.status_code == 204
