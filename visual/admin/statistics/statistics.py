from datetime import date, datetime, timedelta

from flask import render_template, redirect, url_for, request

from visual.core import db
from visual.models import AggregateCount, Tour, Folder, StatSession, Country, City, User
from .. import mod


def get_daterange(delta=31, fmt='%d.%m.%Y'):
    """Парсит GET-параметр daterange, в котором ожидает увидеть строку с диапазоном дат для js-плагина
    daterangepicker, и возвращает кортеж (start, finish, daterange), где start и finish — объекты datetime.date, а
    daterange — отформатированная строка, пригодная для скармливания в value input'а.
    Если параметра нет, возвращает диапазон за последний 31 день.
    """
    r = request.args.get('daterange')
    if r:
        s, e = r.split('-')
        start = datetime.strptime(s.strip(), fmt).date()
        finish = datetime.strptime(e.strip(), fmt).date()
    else:
        start = date.today() - timedelta(days=delta)
        finish = date.today()

    daterange = '{} - {}'.format(start.strftime(fmt), finish.strftime(fmt))

    return start, finish, daterange


@mod.route('/statistics/')
def statistics():
    history_q = db.session\
        .query(
            AggregateCount.date, db.func.sum(AggregateCount.count_uuids), db.func.sum(AggregateCount.count_sessions)
        ) \
        .filter(AggregateCount.aggr_type == 'day') \
        .group_by(AggregateCount.date) \
        .order_by(AggregateCount.date)

    return render_template('admin/statistics/index.html', history=history_q.all())


@mod.route('/statistics/top-tours/')
def statistics_top_tours():
    start, finish, daterange = get_daterange(delta=7)

    top20_q = db.session.query(Tour, db.func.sum(AggregateCount.count_uuids)) \
        .join(AggregateCount) \
        .outerjoin(User, Tour.user_id == User.id) \
        .outerjoin(Folder, Tour.folder_id == Folder.id) \
        .filter(AggregateCount.aggr_type == 'day') \
        .filter(db.func.date(AggregateCount.date).between(start, finish)) \
        .group_by(Tour.id, User.id, Folder.id) \
        .order_by(db.func.sum(AggregateCount.count_uuids).desc()) \
        .limit(20) \
        .options(db.contains_eager(Tour.user), db.contains_eager(Tour.folder))

    return render_template('admin/statistics/top_tours.html', top20=top20_q.all(), daterange=daterange)


@mod.route('/statistics/top-users/')
def statistics_top_users():
    start, finish, daterange = get_daterange(delta=7)

    top20_q = db.session.query(User, db.func.sum(AggregateCount.count_uuids)) \
        .select_from(AggregateCount) \
        .join(Tour, Tour.id == AggregateCount.tour_id == Tour.id) \
        .join(User, User.id == Tour.user_id) \
        .filter(AggregateCount.aggr_type == 'day') \
        .filter(db.func.date(AggregateCount.date).between(start, finish)) \
        .group_by(User.id) \
        .order_by(db.func.sum(AggregateCount.count_uuids).desc()) \
        .limit(20) \

    return render_template('admin/statistics/top_folders.html', top20=top20_q.all(), daterange=daterange)


@mod.route('/statistics/rejects/')
def statistics_rejects():
    start, finish, daterange = get_daterange()

    rejects_q = db.session\
        .query(
            db.func.date(StatSession.start),
            db.func.count('*'),
            db.func.count(db.case([
                (StatSession.time_in_session == '0:0:0', 1)
            ]))
        ) \
        .filter(db.func.date(StatSession.start).between(start, finish)) \
        .group_by(db.func.date(StatSession.start))\
        .order_by(db.func.date(StatSession.start))

    rejects = []
    for row in rejects_q.all():
        rejects.append({
            'date': row[0],
            'total': row[1],
            'rejects': row[2],
            'fraction': int(row[2] / row[1] * 100) if row[1] else 0
        })

    return render_template('admin/statistics/rejects.html', rejects=rejects, daterange=daterange)


@mod.route('/statistics/geo/')
def statistics_geo():
    start, finish, daterange = get_daterange()

    geo_q = db.session\
        .query(db.func.count(StatSession.session_key), Country.name_ru, City.name_ru) \
        .outerjoin(City, StatSession.city_id == City.id) \
        .outerjoin(Country, City.country_id == Country.id) \
        .filter(db.func.date(StatSession.start).between(start, finish)) \
        .group_by(Country.name_ru, City.name_ru) \
        .order_by(db.func.count(StatSession.session_key).desc()) \
        .limit(10)

    geo = []
    for row in geo_q.all():
        geo.append({'city': '{}, {}'.format(row[1] or '???', row[2] or '???'), 'n': row[0]})

    return render_template('admin/statistics/geo.html', geo=geo, daterange=daterange)


@mod.route('/statistics/referers/')
def statistics_referers():
    start, finish, daterange = get_daterange()

    referers_q = db.session \
        .query(StatSession.referer_host, db.func.count()) \
        .filter(db.func.date(StatSession.start).between(start, finish)) \
        .group_by(StatSession.referer_host) \
        .order_by(db.func.count().desc()) \
        .limit(10)

    referers = []
    for row in referers_q.all():
        referers.append({'host': row[0] or 'Прямой переход', 'n': row[1]})

    return render_template('admin/statistics/referers.html', referers=referers, daterange=daterange)


@mod.route('/statistics/devices/')
def statistics_devices():
    q = db.session.query(StatSession.device_type, StatSession.device_brand, db.func.count('*')) \
        .filter(StatSession.device_type != None) \
        .group_by(StatSession.device_type, StatSession.device_brand) \
        .order_by(db.func.count('*').desc()) \

    device_type_names = {StatSession.DEVICE_PC: 'Десктопы', StatSession.DEVICE_TABLET: 'Планшеты', StatSession.DEVICE_MOBILE: 'Мобильные'}
    device_types = {1: 0, 2: 0, 3: 0}
    devices = {}
    for row in q.all():
        device_types[row[0]] += row[2]
        if row[0] in (StatSession.DEVICE_MOBILE, StatSession.DEVICE_TABLET):
            devices.setdefault(row[1], 0)
            devices[row[1]] += row[2]

    device_types = [{'type': device_type_names[t], 'n': n} for t, n in device_types.items()]
    devices = [{'brand': b or 'Не определено', 'n': n} for b, n in devices.items()]

    return render_template('admin/statistics/devices.html', device_types=device_types, devices=devices)


@mod.route('/statistics/systems/')
def statistics_systems():
    q = db.session.query(StatSession.os_family, db.func.count('*')) \
        .filter(StatSession.os_family != None) \
        .group_by(StatSession.os_family) \
        .order_by(db.func.count('*').desc())

    oses = []
    for row in q.all():
        oses.append({'os': row[0], 'n': row[1]})

    q = db.session.query(StatSession.browser_family, db.func.count('*')) \
        .filter(StatSession.browser_family != None) \
        .group_by(StatSession.browser_family) \
        .order_by(db.func.count('*').desc())

    browsers = []
    for row in q.all():
        browsers.append({'browser': row[0], 'n': row[1]})

    return render_template('admin/statistics/systems.html', oses=oses, browsers=browsers)
