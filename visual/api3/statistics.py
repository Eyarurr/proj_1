"""
Статистика туров
"""
import datetime
import json

from flask_babel import gettext
from flask_login import current_user
from flask import request, current_app, g, abort

from . import mod, api_response
from visual.models import Tour, Footage, AggregateCount, AggregateCity, City, Country, AggregateTime, AGGR_TYPES
from visual.core import db
from .common import load_tour_view


def validate_date(s, name):
    if s is None:
        return None
    try:
        d = datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        abort(400, gettext('Invalid %(property)s value', property=name))

    return d


@mod.route('/tours/<int:tour_id>/statistics/traffic')
def stat_get_traffic(tour_id):
    """
    Статистика посещаемости
    GET:
        - quantization: 'hour', 'day', 'month', 'year', default='year'
        - since: date YYYY-MM-DD HH:MM:SS, default - от начала времён
        - until: date, default - по настоящий момент
    :param tour_id:
    :return:
    """
    tour = load_tour_view(tour_id)

    quantization = request.args.get('quantization', 'day')
    if quantization not in AGGR_TYPES:
        abort(400, gettext('Invalid %(property)s value', property='quantization'))

    since = validate_date(request.args.get('since'), 'since')
    until = validate_date(request.args.get('until'), 'until')

    q = AggregateCount.query.filter(AggregateCount.tour_id == tour.id, AggregateCount.aggr_type == quantization)
    if since:
        q = q.filter(AggregateCount.date >= since)
    if until:
        q = q.filter(AggregateCount.date <= until)
    q = q.order_by(AggregateCount.date)

    result = []
    for row in q.all():
        result.append({'ts': row.date, 'hits': row.count_sessions, 'hosts': row.count_uuids})

    return api_response(result)


@mod.route('/tours/<int:tour_id>/statistics/geo/<what>')
def stat_get_geo(tour_id, what):
    """
    Статистика по географии
    GET:
        - since: date YYYY-MM-DD HH:MM:SS, default - от начала времён
        - until: date, default - по настоящий момент
        - limit: Сколько отдавать наиболее популярных городов. ПО умолчанию - 100.
    :param tour_id:
    :return:
    """
    tour = load_tour_view(tour_id)

    since = validate_date(request.args.get('since'), 'since')
    until = validate_date(request.args.get('until'), 'until')
    limit = request.args.get('limit', 100)

    if what == 'cities':
        q = db.session.query(AggregateCity.city_id, City.name, Country.id, Country.name, db.func.sum(AggregateCity.count)) \
            .filter(AggregateCity.tour_id == tour.id) \
            .outerjoin(City, AggregateCity.city_id == City.id) \
            .outerjoin(Country, City.country_id == Country.id) \
            .group_by(AggregateCity.city_id, City.name, Country.id) \
            .order_by(db.func.sum(AggregateCity.count).desc())
    elif what == 'countries':
        q = db.session.query(Country.id, Country.name, db.func.sum(AggregateCity.count)) \
            .filter(AggregateCity.tour_id == tour.id) \
            .outerjoin(City, AggregateCity.city_id == City.id) \
            .outerjoin(Country, City.country_id == Country.id) \
            .group_by(Country.id) \
            .order_by(db.func.sum(AggregateCity.count).desc())

    if since or until:
        q = q.filter(AggregateCity.aggr_type == 'day')
    else:
        q = q.filter(AggregateCity.aggr_type == 'year')
    if since:
        q = q.filter(AggregateCity.date >= since)
    if until:
        q = q.filter(AggregateCity.date <= until)
    if limit:
        q = q.limit(limit)

    result = {}
    if what == 'cities':
        for city_id, city_name, country_code, country_name, cnt in q.all():
            result[city_id] = {'n': cnt, 'city': city_name, 'country': country_name, 'cc': country_code}
    elif what == 'countries':
        for country_code, country_name, cnt in q.all():
            result[country_code] = {'n': cnt, 'country': country_name}

    return api_response(result)


@mod.route('/tours/<int:tour_id>/statistics/time')
def stat_get_time(tour_id):
    """
    Статистика по географии
    """
    tour = load_tour_view(tour_id)

    stat = AggregateTime.query.get(tour.id)

    if stat is None:
        return api_response(None)

    # В автотестах не происходит конвертация поля count_json в dict. @todo: разобраться.
    if type(stat.count_json) is str:
        stat.count_json = json.loads(stat.count_json)

    result = stat.count_json
    result.update({
        'min': stat.min.seconds,
        'max': stat.max.seconds,
        'mid': stat.mid.seconds
    })

    return api_response(result)
