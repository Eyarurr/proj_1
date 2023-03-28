import os
import json
import datetime

import pytest

from tests.conftest import SRC_DIR
from visual import create_app
from visual.core import db
from visual.models import User, Footage, Tour, TeamMember, AuthToken
from visual.models import City, Country, AggregateCount, StatSession, AggregateTime, AggregateCity, \
    AggregateReferer, LastAggregateDate

CITY_IDS = [524901, 2988507, 5375480, 2861096, 498817, 2017370, 2867714, 294640, 5808079, 2921044, 4744870, 2977824,
            3017382, 523812, 550280]
USERS = {}
TOURS = {}

datasets = {
    'statistic_traffic': [
        {'id': 1, 'query_string': {'quantization': 'hour', }},
        {'id': 2, 'query_string': {'quantization': 'day', 'since': '2020-01-01 13:00:00', 'until': '2021-01-01 13:00:00'}},
        {'id': 3, 'query_string': {'quantization': 'month', 'since': '2020-01-01 13:00:00', 'until': '2021-01-01 13:00:00'}},
        {'id': 4, 'query_string': {'quantization': 'year', 'since': '2020-01-01 13:00:00', 'until': '2021-01-01 13:00:00'}},
    ],
    'statistic_geo':
        {'id': 1, 'query_string': {'limit': 1000, 'since': '2020-01-01 13:00:00', 'until': '2021-01-01 13:00:00'}},
}


with open(os.path.join(SRC_DIR, 'stats.json')) as fh:
    stat_sessions = json.load(fh)


def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3, 6 - нормальные, 4 - забаненный и 5 - удалённый
    Всем, кроме 6 добавляем подписку virtoaster-trial
    Создаем по одному туры и съемке каждому юзеру.
    Из src/stats.json распаковываем агрегационные данные для одного тура.
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

            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title')}

        db.session.add(Country(id=1, name_en='US'))
        db.session.flush()
        for city in CITY_IDS:
            db.session.add(City(id=city, country_id=1, name_en=f'Some_City_{city}'))
            db.session.flush()
        
        for item in stat_sessions['stat_sessions']:
            db.session.add(StatSession(**item))
        for item in stat_sessions['stat_city']:
            db.session.add(AggregateCity(**item))
        for item in stat_sessions['stat_count']:
            db.session.add(AggregateCount(**item))
        for item in stat_sessions['stat_date_aggregate']:
            db.session.add(LastAggregateDate(**item))
        for item in stat_sessions['stat_referer']:
            db.session.add(AggregateReferer(**item))
        for item in stat_sessions['stat_time']:
            db.session.add(AggregateTime(**item))
        db.session.commit()
        db.session.close()


def test_stat_traffic(api):
    """
    Статистика посещаемости
    GET /tours/<tour_id>/statistics/traffic

    GET-параметры:
    quantization. По каким интервалам отдавать статистику: hour, day, month, year. Default=day.
    since. Время в формате YYYY-MM-DD HH:MM:SS, начиная с которой отдавать данные. Если не указано, отдаётся статистика от рождения тура.
    until. Время в формате YYYY-MM-DD HH:MM:SS, до которого включительно отдавать данные. Если не указано, отдаётся до настоящего момента.
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        for dataset in datasets['statistic_traffic']:

            # Описание: Пытаемся статистику посещаемости
            # Параметры: С токеном авторизации
            # Ожидаемый результат: Можно получить статистику, только не забаненного и удаленного юзера
            # если юзера есть подписка 'virtoaster'

            resp = api.get(f'/tours/{tour_id}/statistics/traffic', query_string=dataset['query_string'])
            if user['banned'] or user['deleted'] or user_id == 6:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 200
                assert resp.result is not None

            # Описание: Пытаемся статистику посещаемости
            # Параметры: С токеном авторизации
            # Ожидаемый результат: Любой может получить статистику, кроме забаненного юзера
            # если юзера есть подписка 'virtoaster'

            resp = api.get(f'/tours/{tour_id}/statistics/traffic', query_string=dataset['query_string'], auth_as=user['email'])
            if user['banned']:
                assert resp.status_code == 403
            else:
                assert resp.status_code == 200
                assert resp.result is not None


def test_stat_countries(api):
    """
    География по странам
    GET /tours/<tour_id>/stats/geo/countries

    GET-параметры:
    since. Время в формате YYYY-MM-DD HH:MM:SS, начиная с которой отдавать данные. Если не указано, отдаётся статистика от рождения тура.
    until. Время в формате YYYY-MM-DD HH:MM:SS, до которого включительно отдавать данные. Если не указано, отдаётся до настоящего момента.
    limit. Сколько отдавать наиболее популярных городов. ПО умолчанию - 100.
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        dataset = datasets['statistic_geo']

        # Описание: Пытаемся статистику по странам
        # Параметры: С токеном авторизации
        # Ожидаемый результат: Можно получить статистику, только не забаненного и удаленного юзера
        # если юзера есть подписка 'virtoaster'

        resp = api.get(f'/tours/{tour_id}/statistics/geo/countries', query_string=dataset['query_string'])
        if user['banned'] or user['deleted'] or user_id == 6:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200
            assert resp.result is not None

        # Описание: Пытаемся статистику по странам
        # Параметры: С токеном авторизации
        # Ожидаемый результат: Любой может получить статистику, кроме забаненного юзера
        resp = api.get(f'/tours/{tour_id}/statistics/geo/countries', auth_as=user['email'], query_string=dataset['query_string'])
        if user['banned']:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200
            assert resp.result is not None


def test_stat_cities(api):
    """
    География по городам
    GET /tours/<tour_id>/stats/geo/cities

    GET-параметры:
    since. Время в формате YYYY-MM-DD HH:MM:SS, начиная с которой отдавать данные. Если не указано, отдаётся статистика от рождения тура.
    until. Время в формате YYYY-MM-DD HH:MM:SS, до которого включительно отдавать данные. Если не указано, отдаётся до настоящего момента.
    limit. Сколько отдавать наиболее популярных городов. ПО умолчанию - 100.
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        dataset = datasets['statistic_geo']

        # Описание: Пытаемся статистику по городам
        # Параметры: С токеном авторизации
        # Ожидаемый результат: Можно получить статистику, только не забаненного и удаленного юзера
        resp = api.get(f'/tours/{tour_id}/statistics/geo/cities', query_string=dataset['query_string'])
        if user['banned'] or user['deleted'] or user_id == 6:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200
            assert resp.result is not None

        # Описание: Пытаемся статистику по городам
        # Параметры: С токеном авторизации
        # Ожидаемый результат: Любой может получить статистику, кроме забаненного юзера
        resp = api.get(f'/tours/{tour_id}/statistics/geo/cities', auth_as=user['email'], query_string=dataset['query_string'])
        if user['banned']:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200
            assert resp.result is not None


def test_stat_time(api):
    """
    Время в туре
    GET /tours/<tour_id>/statistics/time
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        # Описание: Пытаемся узнать о том, сколько времени юзеры проводят в туре
        # Параметры: Без токена авторизации
        # Ожидаемый результат: Можно получить статистику, только не забаненного и удаленного юзера
        resp = api.get(f'/tours/{tour_id}/statistics/time')
        if user['banned'] or user['deleted'] or user_id == 6:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200

        # Описание: Пытаемся узнать о том, сколько времени юзеры проводят в туре
        # Параметры: С токеном авторизации
        # Ожидаемый результат: Любой может получить статистику, кроме забаненного юзера
        resp = api.get(f'/tours/{tour_id}/statistics/time', auth_as=user['email'],)
        if user['banned']:
            assert resp.status_code == 403
        else:
            assert resp.status_code == 200


@pytest.mark.bad_requests
def test_exceptions(api):
    """
    Плохие запросы
    """
    # Параметр: Несуществующий тур
    user_id = 1
    user = USERS[user_id]
    tour_id = user_id
    resp = api.get(f'/tours/100/statistics/traffic')
    assert resp.errors
    assert resp.status_code == 404
    assert resp.has_error('Tour not found.')

    # Неверное значение свойство quantization
    query_string = {'quantization': 'some_val', 'since': '2020-01-01 13:00:00', 'until': '2021-01-01 13:00:00'}
    resp = api.get(f'/tours/{tour_id}/statistics/traffic', query_string=query_string,)
    assert resp.errors
    assert resp.status_code == 400
    assert resp.has_error('Invalid quantization value')

    # Неверное значение для since
    query_string = {'quantization': 'day', 'since': 'some_val', 'until': '2021-01-01 13:00:00'}
    resp = api.get(f'/tours/{tour_id}/statistics/traffic', query_string=query_string)
    assert resp.errors
    assert resp.status_code == 400
    assert resp.has_error('Invalid since value')

    # Неверное значение для until
    query_string = {'quantization': 'day', 'since': '2021-01-01 13:00:00', 'until': 'some_val'}
    resp = api.get(f'/tours/{tour_id}/statistics/traffic', query_string=query_string)
    assert resp.errors
    assert resp.status_code == 400
    assert resp.has_error('Invalid until value')

    # Указан только since
    query_string = {'quantization': 'day', 'since': '2021-01-01 13:00:00'}
    resp = api.get(f'/tours/{tour_id}/statistics/traffic', query_string=query_string)
    assert resp.status_code == 200

    urls = (f'/tours/{tour_id}/statistics/geo/countries', f'/tours/{tour_id}/statistics/geo/cities')
    for url in urls:

        # Неверное значение для until
        query_string = {'limit': 1000, 'since': 'some', 'until': '2021-01-01 13:00:00'}
        resp = api.get(url, query_string=query_string)
        assert resp.errors
        assert resp.status_code == 400
        assert resp.has_error('Invalid since value')

        # Неверное значение для until
        query_string = {'limit': 1000, 'since': '2021-01-01 13:00:00', 'until': 'some'}
        resp = api.get(url, query_string=query_string)
        assert resp.errors
        assert resp.status_code == 400
        assert resp.has_error('Invalid until value')

