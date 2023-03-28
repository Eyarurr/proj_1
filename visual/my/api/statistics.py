import copy
from datetime import datetime, timedelta
from collections import OrderedDict

from pytz import timezone
from flask import jsonify, request, current_app
from flask_login import current_user
from flask_babel import gettext, format_datetime, get_timezone, format_timedelta, lazy_gettext

from visual.my import mod
from visual.models import Tour, AggregateCount, AggregateCity, AggregateTime, AggregateReferer, City, Country
from visual.core import db


TIME_FORMAT = {'hour': 'yyyy-MM-dd HH:mm:ss',
               'day': 'yyyy-MM-dd HH:mm:ss',
               'month': 'yyyy-MM-dd HH:mm:ss',
               'year': 'yyyy-MM-dd HH:mm:ss'}

TIME_INTERVAL = OrderedDict([("0", lazy_gettext('Rejection')),
                             ("10", lazy_gettext('0 — 10 sec.')),
                             ("60", lazy_gettext('10 — 60 sec.')),
                             ("300", lazy_gettext('1 — 5 min.')),
                             ("600", lazy_gettext('5 — 10 min.')),
                             ("1800", lazy_gettext('10 — 30 min.')),
                             ("3600", lazy_gettext('30 — 60 min.')),
                             ("+3600", lazy_gettext('Over an hour'))])


def check_access(query):
    """
    Для не-членов команды добавляет в запрос условие: только для своих объектов.
    :param query: BaseQuery
    :return: BaseQuery
    """
    if not current_user.team_member:
        return query.filter(Estate.user_id == current_user.id)
    return query


def get_tours_ids():
    tours_query = check_access(db.session.query(Tour.id).join(Estate, Tour.estate_id == Estate.id))
    available_tours = [value[0] for value in tours_query.all()]
    tours_id = []
    for id in request.args.get('tours_id', '').split(','):
        try:
            if int(id) in available_tours:
                tours_id.append(int(id))
        except ValueError:
            pass
    return tours_id


def get_estates_tours_ids():
    estates_tours_id = []
    for id in request.args.get('estates_id', '').split(','):
        try:
            estates_tours_id.append(int(id))
        except ValueError:
            pass
    if estates_tours_id:
        estates_tour_query = db.session.query(Tour.estate_id, db.func.array_agg(Tour.id)).\
            join(Estate, Tour.estate_id == Estate.id). \
            filter(Tour.estate_id.in_(estates_tours_id)).group_by(Tour.estate_id)

        estates_tour_query = check_access(estates_tour_query)
        estates_tours_id = estates_tour_query.all()
    return estates_tours_id


def get_start_end_values(group):
    hour_now = datetime.now(tz=get_timezone()).replace(minute=0, second=0, microsecond=0)
    today = hour_now.replace(hour=0)
    month_now = today.replace(day=1)
    year_now = month_now.replace(month=1)

    if group == 'hour':
        date_start = hour_now - timedelta(days=current_app.config['HISTORY_DEPTH_HOURS'])
        date_end = hour_now
    if group == 'day':
        date_start = past_year_date(today, current_app.config['HISTORY_DEPTH_DAYS'])
        date_end = today
    if group == 'month':
        date_start = past_year_date(month_now, current_app.config['HISTORY_DEPTH_MONTHS'])
        date_end = month_now
    if group == 'year':
        date_start = past_year_date(year_now, current_app.config['HISTORY_DEPTH_YEARS'])
        date_end = year_now

    try:
        date_start = datetime.strptime(request.args.get('date_start'), "%Y-%m-%d").replace(tzinfo=get_timezone())
    except (TypeError, ValueError):
        pass
    try:
        date_end = datetime.strptime(request.args.get('date_end'), "%Y-%m-%d").replace(tzinfo=get_timezone())
    except (TypeError, ValueError):
        pass

    if group == 'hour':
        if date_end >= today:
            date_end = hour_now
        else:
            date_end = date_end.replace(hour=23)
        date_start = date_start.astimezone(timezone('UTC'))
        date_end = date_end.astimezone(timezone('UTC'))
    else:
        date_start = date_start.replace(tzinfo=timezone('UTC'))
        date_end = date_end.replace(tzinfo=timezone('UTC'))
    if group == 'month':
        date_start = date_start.replace(day=1)
        date_end = date_end.replace(day=1)
    if group == 'year':
        date_start = date_start.replace(month=1, day=1)
        date_end = date_end.replace(month=1, day=1)
    return date_start, date_end


def start_date_correction(group, start_date, tours_id):
    min_date = db.session.query(AggregateCount.date).order_by(AggregateCount.date).\
        filter(AggregateCount.aggr_type == group, AggregateCount.tour_id.in_(tours_id)).first()
    if min_date is None:
        return start_date
    return start_date if start_date > min_date[0] else min_date[0]


def assembling_nodes(query, tours_id, estates_tours_id, data_model, container, assembling_node_func, *args):
    stat_data = {'tours': {},
                 'estates': {}}
    if tours_id:
        for tour_id in tours_id:
            stat_data['tours'][str(tour_id)] = copy.deepcopy(container)
        tours_data = query.add_column(data_model.tour_id).filter(data_model.tour_id.in_(tours_id)). \
            group_by(data_model.tour_id).all()
        for data in tours_data:
            tour_id = str(data[-1])
            assembling_node_func(stat_data['tours'][tour_id], data[:-1], *args)

    if estates_tours_id:
        for estate_id, tours_id in estates_tours_id:
            stat_data['estates'][estate_id] = copy.deepcopy(container)
            for data in query.filter(data_model.tour_id.in_(tours_id)).all():
                assembling_node_func(stat_data['estates'][estate_id], data, *args)
    return stat_data


def assembling_time_node(container, fields):
    def timedelta_formater(delta):
        if delta.days > 0:
            return '> {}'.format(format_timedelta(timedelta(days=1), threshold=1.0))
        else:
            time_interval = []
            minutes, seconds = divmod(delta.seconds, 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                time_interval.append(format_timedelta(timedelta(hours=hours), threshold=1.0))
            if minutes > 0:
                time_interval.append(format_timedelta(timedelta(minutes=minutes), threshold=1.0))
            time_interval.append(format_timedelta(timedelta(seconds=seconds), threshold=1.0))
            return ' '.join(time_interval[:2])

    for key, value in zip(('min', 'max', 'mid', 'json'), fields):
        if key == 'json':
            tmp = OrderedDict.fromkeys(TIME_INTERVAL.values(), 0)
            if value is not None:
                for counter in value:
                    for key, value in counter.items():
                        tmp[TIME_INTERVAL[key]] = tmp[TIME_INTERVAL[key]] + value
                container['values'] = list(tmp.values())
        elif key == 'mid':
            if value is not None:
                container[str(key)] = timedelta_formater(sorted(value)[int(len(value)/2)])
            else:
                container[str(key)] = timedelta_formater(timedelta(days=0))
        else:
            if value and key != 'date':
                container[str(key)] = timedelta_formater(value)


def assembling_traffic_node(container, fields, group, date_interval):
    tmp = {}
    date = format_datetime(fields[0], format=TIME_FORMAT[group])
    for key, value in zip(('users', 'visits'), fields[1:]):
        tmp[str(key)] = int(value)
    try:
        index = date_interval.index(date)
        container['values'][index] = tmp
    except:
        pass


def assembling_node(container, fields, field_type):
    def formater(value, key):
        if key in 'visits':
            return int(value) if value is not None else 0
        elif key == 'iframe':
            return value
        else:
            return str(value) if value is not None else ''
    tmp = {}
    for key, value in zip(field_type, fields):
        if key != 'date':
            tmp[str(key)] = formater(value, key)
    container['total'].append(tmp)


def past_year_date(date, count_years):
    year = date.year - count_years
    return date.replace(year=year)


def timedelta_round_increment(date, type):
    if type == 'hour':
        return date + timedelta(hours=1)
    if type == 'day':
        return date + timedelta(days=1)
    year, month = date.year, date.month
    if type == 'month':
        month += 1
    else:
        year += 1
    if month > 12:
        month = 1
        year += 1
    return datetime(year=year, month=month, day=1, tzinfo=timezone('UTC'))


def get_date_interval(date_start, date_end, group):
    time_format = TIME_FORMAT[group]
    interval = []

    if date_start > date_end:
        return interval

    iter_date = date_start
    stop_date = date_end
    if group == 'month':
        iter_date = iter_date.replace(day=1)
        stop_date = stop_date.replace(day=1)
    if group == 'year':
        iter_date = iter_date.replace(month=1, day=1)
        stop_date = stop_date.replace(month=1, day=1)

    while iter_date <= stop_date:
        interval.append(format_datetime(iter_date.astimezone(get_timezone()), format=time_format))
        iter_date = timedelta_round_increment(iter_date, group)

    return interval


def get_top_values(estates, union, key, count_top_values=10):
    union_copy = copy.deepcopy(union)
    tmp = []
    for num, element in enumerate(estates):
        if element[key] == union_copy[key]:
            union_copy['visits'] = element['visits']
            count_top_values += 1
        else:
            if num < count_top_values:
                tmp.append(element)
            else:
                union_copy['visits'] += element['visits']
    if union_copy['visits'] != 0:
        tmp.append(union_copy)
    return tmp


@mod.route('/statistics/api/')
@mod.route('/statistics/api/<query_type>')
def statistic_api(query_type=None):
    current_app.logger.warning('Используется API 2.0: {}?{}'.format(request.path, request.query_string.decode()))
    stat_data = {'tours': {},
                 'estates': {}}

    # Проверка наличия туров и объектов в запросе
    if not bool({'estates_id', 'tours_id'} & set(request.args.keys())):
        return jsonify({"error": "Empty value in 'estates_id' and 'tours_id'"})

    # Валидация туров
    tours_id = get_tours_ids()
    estates_tours_id = get_estates_tours_ids()

    # Проверка прохождения валидации
    if (not bool(tours_id)) and (not bool(estates_tours_id)):
        return jsonify({"error": "Access is denied"})

    # Статистика времени нахождения в туре
    if query_type == 'time':
        q = db.session.query(db.func.min(AggregateTime.min),
                             db.func.max(AggregateTime.max),
                             db.func.array_agg(AggregateTime.mid),
                             db.func.array_agg(AggregateTime.count_json)). \
            order_by(db.func.max(AggregateTime.max).desc())

        value = {'values': [0 for _ in TIME_INTERVAL.values()]}
        stat_data = assembling_nodes(q, tours_id, estates_tours_id, AggregateTime, value, assembling_time_node)
        stat_data['time'] = list(TIME_INTERVAL.values())
        return jsonify(stat_data)

    # Определение периода статистики
    group = request.args.get('group', 'months')[:-1]
    if group not in TIME_FORMAT.keys():
        stat_data['error'] = "group not found in ({}s)".format("s, ".join(TIME_FORMAT.keys()))
        return jsonify(stat_data)

    date_start, date_end = get_start_end_values(group)

    # Статистика посещаемости по времени
    if query_type == 'traffic':

        all_tours_id = set(sum([estates_tours[1] for estates_tours in estates_tours_id], tours_id))
        date_start = start_date_correction(group, date_start, all_tours_id)

        date_interval = get_date_interval(date_start, date_end, group)
        container = {'values': [{'users': 0, 'visits': 0} for _ in date_interval]}

        q = db.session.query(AggregateCount.date,
                             db.func.sum(AggregateCount.count_uuids),
                             db.func.sum(AggregateCount.count_sessions)).group_by(AggregateCount.date). \
            order_by(AggregateCount.date, db.func.sum(AggregateCount.count_uuids).desc())

        # Фильтр по периоду выдачи статистики
        q = q.filter(AggregateCount.aggr_type == group,
                     AggregateCount.date >= date_start,
                     AggregateCount.date <= date_end)

        # Сборка статистики по турам и объектам статистики
        stat_data = assembling_nodes(q, tours_id, estates_tours_id, AggregateCount, container, assembling_traffic_node,
                                     group, date_interval)

        # Вывод интервала времени
        stat_data['date'] = date_interval
        return jsonify(stat_data)


    # Выбор типа api
    QUERY = {'geo': (AggregateCity,
                     ('date', 'city', 'country', 'visits'),
                     db.session.query(AggregateCity.date,
                                      City.get_name_field(),
                                      Country.get_name_field(),
                                      db.func.sum(AggregateCity.count)). \
                         outerjoin(City, City.id == AggregateCity.city_id). \
                         outerjoin(Country, Country.id == City.country_id). \
                         group_by(AggregateCity.date,
                                  City.get_name_field(),
                                  Country.get_name_field()). \
                         order_by(AggregateCity.date, db.func.sum(AggregateCity.count).desc())),
             'sources': (AggregateReferer,
                         ('date', 'referer_host', 'iframe', 'visits'),
                         db.session.query(AggregateReferer.date,
                                          AggregateReferer.referer_host,
                                          AggregateReferer.iframe,
                                          db.func.sum(AggregateReferer.count)).group_by(AggregateReferer.date,
                                                                                        AggregateReferer.referer_host,
                                                                                        AggregateReferer.iframe). \
                            order_by(AggregateReferer.date, db.func.sum(AggregateReferer.count).desc()))}

    if query_type not in QUERY.keys():
        stat_data['error'] = "Type '{}' not found in API."
        return jsonify(stat_data)

    data_model, type_field, q = QUERY[query_type]

    # Фильтр по периоду выдачи статистики
    q = q.filter(data_model.aggr_type == group, data_model.date == date_start)
    # Фильтр по полю iframe
    if query_type == 'sources' and request.args.get('iframe') is not None:
        try:
            iframe = int(request.args.get('iframe')) == 1
        except ValueError:
            stat_data['error'] = "iframe must be 0 or 1"
            return jsonify(stat_data)
        q = q.filter(AggregateReferer.iframe == iframe)

    # Сборка статистики по турам и объектам статистики
    stat_data = assembling_nodes(q, tours_id, estates_tours_id, data_model, {'total': []}, assembling_node, type_field)

    # Собираем топ 10 в estates и tours
    if query_type == 'sources':
        union = {'referer_host': gettext("Others"), 'iframe': '', 'visits': 0}
        key = 'referer_host'
    else:
        r = db.session\
            .query(City.get_name_field(), Country.get_name_field()) \
            .outerjoin(Country, Country.id == City.country_id) \
            .filter(City.id == 0) \
            .first()
        if r is None:
            city, country = 0, 0
        else:
            city, country = r
        union = {'city': city, 'country': country, 'visits': 0}
        key = 'city'

    for data_type in ['estates', 'tours']:
        if stat_data[data_type]:
            for data in stat_data[data_type].values():
                data['total'] = get_top_values(data['total'], union, key)

    return jsonify(stat_data)
