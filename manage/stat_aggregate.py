import os
import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from statistics import median

from flask import current_app
from sqlalchemy import or_

from visual.core import db
from visual.mail import send_email
from visual.models import StatSession, AggregateTime, AggregateCity, AggregateReferer, \
    LastAggregateDate, AggregateCount, Tour, User

LOCK_FILE = '/tmp/stat_aggregate.lock'


class StatAggregate:
    """Пересчитывает статистику в агрегационных таблицах из stat_sessions в заданном интервале"""
    def run(self, updated_tables, tour_ids=None, folder_id=None, user_id=None, user_email=None, interval=None):
        self.log = logging.getLogger('statistics')

        if interval:
            try:
                start_date = interval.split('...')[0]
                end_date = interval.split('...')[1]
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d')

                count_all = db.session \
                    .query(db.func.count('*')) \
                    .filter(db.func.date(StatSession.start).between(start_date, end_date)) \
                    .group_by(db.func.date(StatSession.start)) \
                    .order_by(db.func.date(StatSession.start)).all()
                try:
                    data_quality = 100 * len(count_all) / (end_datetime-start_datetime).days
                    if data_quality < 100:
                        prompt = 'Внимание! В наличии только %0.2f %% данных за данный период. Хотите продолжить? (Yes)'\
                                 % data_quality
                        if input(prompt) != "Yes":
                            print("Bye!")
                            return

                except ZeroDivisionError:
                    self.log.warning("Временной интервал слишком мал.")
                    return
            except ValueError:
                self.log.warning("Параметр interval неверного формата.")
                return
        else:
            self.log.warning("Не задан параметр interval.")
            return

        if tour_ids is not None:
            try:
                tour_ids = [int(id) for id in tour_ids.split(',')]
            except:
                self.log.warning("Параметр --tour-ids неверного формата.")
                return
        else:
            tour_ids = []

        if folder_id is not None:
            folder_tour_ids = db.session.query(Tour.id).filter(Tour.folder_id == folder_id).all()
            if folder_tour_ids:
                tour_ids = list(set(tour_ids) | {id[0] for id in folder_tour_ids})
            else:
                self.log.warning("Папка пуста.")

        if user_id is not None:
            user_tour_ids = db.session.query(Tour.id).filter(Tour.user_id == user_id).all()
            if user_tour_ids:
                tour_ids = list(set(tour_ids) | {id[0] for id in user_tour_ids})
            else:
                self.log.warning("У юзера нет туров.")

        if user_email is not None:
            user_tour_ids = db.session.query(Tour.id).join(User, User.id == Tour.user_id).\
                filter(User.email == user_email).all()
            if user_tour_ids:
                tour_ids = list(set(tour_ids) | {id[0] for id in user_tour_ids})
            else:
                self.log.warning("У юзера нет туров.")

        if tour_ids:
            aggregate_filter = {'stat_count_filter': 'AND tour_id = ANY(:tour_ids)',
                                'stat_city_filter': 'AND tour_id = ANY(:tour_ids)',
                                'stat_referer_filter': 'AND tour_id = ANY(:tour_ids)'}
        else:
            aggregate_filter = {'stat_count_filter': '',
                                'stat_city_filter': '',
                                'stat_referer_filter': ''}

        for current_table in updated_tables:
            if current_table == 'time':
                continue
            if current_table == 'count':
                model = AggregateCount
            elif current_table == 'city':
                model = AggregateCity
            elif current_table == 'referer':
                model = AggregateReferer
            else:
                self.log.warning("Неверно указано имя таблицы.")
                return

            trunc_query_between = model.query \
                .filter(model.date.between(start_date, end_date))

            trunc_query_month = model.query \
                .filter(model.aggr_type == 'month') \
                .filter(or_(db.func.DATE(model.date) == db.func.DATE_TRUNC('month', start_datetime),
                            db.func.DATE(model.date) == db.func.DATE_TRUNC('month', end_datetime)))

            trunc_query_year = model.query \
                .filter(model.aggr_type == 'year') \
                .filter(db.func.DATE(model.date) == db.func.DATE_TRUNC('year', start_datetime))

            if tour_ids:
                trunc_query_between = trunc_query_between.filter(model.tour_id.in_(tour_ids))
                trunc_query_month = trunc_query_month.filter(model.tour_id.in_(tour_ids))
                trunc_query_year = trunc_query_year.filter(model.tour_id.in_(tour_ids))

            for trunc_query in [trunc_query_between, trunc_query_month, trunc_query_year]:
                trunc_query.delete(synchronize_session=False)
            db.session.commit()

        month_date_range = []
        current_date = datetime.strptime(start_date, '%Y-%m-%d')
        while current_date <= datetime.strptime(end_date, '%Y-%m-%d'):
            month_date_range.append(current_date)
            current_date = current_date + relativedelta(months=1)

        if 'count' in updated_tables:
            count_query_hour_day = """INSERT INTO stat_count (aggr_type, date, tour_id, count_uuids, count_sessions)
                             (
                                 SELECT 
                                    'hour'::count_type, 
                                    date_trunc('hour', start ), 
                                    tour_id, 
                                    count(is_uniq), 
                                    count(DISTINCT session_key)
                                 FROM stat_sessions
                                 WHERE start > :start_date AND start < :end_date {stat_count_filter}
                                 GROUP BY date_trunc('hour', start ), tour_id
                             )
                             UNION ALL
                             (
                                 SELECT 
                                    'day'::count_type, 
                                    date_trunc('day', start), 
                                    tour_id, 
                                    count(is_uniq), 
                                    count(DISTINCT session_key)
                                 FROM stat_sessions
                                 WHERE start > :start_date AND start < :end_date {stat_count_filter}
                                 GROUP BY date_trunc('day', start ) , tour_id
                             )                             
                             ;""".format(**aggregate_filter)

            db.session.execute(count_query_hour_day, {
                'start_date': start_date,
                'end_date': end_date,
                'tour_ids': tour_ids,
            })
            db.session.commit()

            for month_date in month_date_range:
                count_query_month = """INSERT INTO stat_count (aggr_type, date, tour_id, count_uuids, count_sessions)
                                       (
                                            SELECT 
                                                'month'::count_type, 
                                                date_trunc('month', date :month_date),
                                                tour_id, sum(count_uuids), sum(count_sessions) 
                                            FROM stat_count 
                                            WHERE aggr_type='day' 
                                                AND date between date_trunc('month', date :month_date ) 
                                                AND date_trunc('month', date :month_date ) + interval '1 month' {stat_count_filter} 
                                            GROUP BY date_trunc('month', date :month_date ), tour_id
                                       )
                                       ON CONFLICT ON CONSTRAINT stat_count_pkey DO UPDATE
                                       SET count_uuids=excluded.count_uuids, count_sessions=excluded.count_sessions                                       
                                    ;""".format(**aggregate_filter)

                db.session.execute(count_query_month, {
                    'month_date': month_date.strftime('%Y-%m-%d'),
                    'tour_ids': tour_ids
                })

            for year in list(set(x.year for x in month_date_range)):
                count_query_year = """INSERT INTO stat_count (aggr_type, date, tour_id, count_uuids, count_sessions)
                                       (
                                            SELECT 
                                                'year'::count_type, 
                                                date_trunc('year', DATE :year_date),
                                                tour_id, sum(count_uuids), sum(count_sessions) 
                                            FROM stat_count 
                                            WHERE aggr_type='month' 
                                                AND date between DATE :year_date 
                                                AND DATE :end_date {stat_count_filter} 
                                            GROUP BY date_trunc('year', DATE :year_date ), tour_id
                                       )
                                       ON CONFLICT ON CONSTRAINT stat_count_pkey DO UPDATE
                                       SET count_uuids=excluded.count_uuids, count_sessions=excluded.count_sessions
                                   ;""".format(**aggregate_filter)

                db.session.execute(count_query_year, {
                    'year_date': datetime(year, 1, 1).strftime('%Y-%m-%d'),
                    'end_date': end_date,
                    'tour_ids': tour_ids,
                })


        if 'time' in updated_tables:
            self.update_time(tour_ids=tour_ids)
            if not tour_ids:
                stat_time = LastAggregateDate.query.filter_by(aggregate_table='stat_time').first()
                if stat_time is None:
                    db.session.add(LastAggregateDate(aggregate_table='stat_time',
                                                     date_aggregate=datetime.now()))
                else:
                    stat_time.date_aggregate = datetime.now()


        if 'city' in updated_tables:
            count_query_hour_day = """INSERT INTO stat_city (aggr_type, date, tour_id, city_id, count)
                                     (
                                         SELECT 
                                             'hour'::count_type, 
                                             date_trunc('hour', start), 
                                             tour_id, city_id, count(DISTINCT session_key)
                                         FROM stat_sessions
                                         WHERE start > :start_date AND start < :end_date AND city_id IS NOT NULL {stat_city_filter}
                                         GROUP BY date_trunc('hour', start), tour_id, city_id
                                     )
                                     UNION ALL
                                     (
                                         SELECT 
                                             'day'::count_type, 
                                             date_trunc('day', start), 
                                             tour_id, city_id, count(DISTINCT session_key)
                                         FROM stat_sessions
                                         WHERE start > :start_date AND start < :end_date AND city_id IS NOT NULL {stat_city_filter}
                                         GROUP BY date_trunc('day', start), tour_id, city_id
                                     )
                                     ;""".format(**aggregate_filter)

            db.session.execute(count_query_hour_day, {
                'start_date': start_date,
                'end_date': end_date,
                'tour_ids': tour_ids,
            })
            db.session.commit()

            for month_date in month_date_range:
                count_query_month = """INSERT INTO stat_city (aggr_type, date, tour_id, city_id, count)
                                       (
                                            SELECT 
                                                'month'::count_type, 
                                                date_trunc('month', date :month_date),
                                                tour_id, city_id, sum(count) 
                                            FROM stat_city 
                                            WHERE aggr_type='day'
                                                AND date between date_trunc('month', date :month_date ) 
                                                AND date_trunc('month', date :month_date ) + interval '1 month' {stat_city_filter} 
                                            GROUP BY date_trunc('month', date :month_date ), tour_id, city_id
                                       )
                                       ON CONFLICT ON CONSTRAINT stat_city_pkey DO UPDATE
                                       SET count=excluded.count                                       
                                    ;""".format(**aggregate_filter)

                db.session.execute(count_query_month, {
                    'month_date': month_date.strftime('%Y-%m-%d'),
                    'tour_ids': tour_ids
                })

            for year in list(set(x.year for x in month_date_range)):
                count_query_year = """INSERT INTO stat_city (aggr_type, date, tour_id, city_id, count)
                                       (
                                            SELECT 
                                                'year'::count_type, 
                                                date_trunc('year', DATE :year_date),
                                                tour_id, city_id, sum(count) 
                                            FROM stat_city 
                                            WHERE aggr_type='month' 
                                                AND date between DATE :year_date 
                                                AND DATE :end_date {stat_city_filter} 
                                            GROUP BY date_trunc('year', DATE :year_date ), tour_id, city_id
                                       )
                                       ON CONFLICT ON CONSTRAINT stat_city_pkey DO UPDATE
                                       SET count=excluded.count
                                   ;""".format(**aggregate_filter)

                db.session.execute(count_query_year, {
                    'year_date': datetime(year, 1, 1).strftime('%Y-%m-%d'),
                    'end_date': end_date,
                    'tour_ids': tour_ids,
                })

        if 'referer' in updated_tables:
            count_query_hour_day = """INSERT INTO stat_referer (aggr_type, date, tour_id, referer_host, iframe, count)
                                      (
                                          SELECT 
                                              'hour'::count_type, 
                                              date_trunc('hour', start), 
                                              tour_id, referer_host, iframe, count(DISTINCT session_key)
                                          FROM stat_sessions
                                          WHERE start > :start_date AND start < :end_date {stat_referer_filter}
                                          GROUP BY date_trunc('hour', start), tour_id, referer_host, iframe
                                      )
                                      UNION ALL
                                      (
                                          SELECT 
                                              'day'::count_type, 
                                              date_trunc('day', start), 
                                              tour_id, referer_host, iframe, count(DISTINCT session_key)
                                          FROM stat_sessions
                                          WHERE start > :start_date AND start < :end_date {stat_referer_filter}
                                          GROUP BY date_trunc('day', start), tour_id, referer_host, iframe
                                     )
                                     ;""".format(**aggregate_filter)

            db.session.execute(count_query_hour_day, {
                'start_date': start_date,
                'end_date': end_date,
                'tour_ids': tour_ids,
            })
            db.session.commit()

            for month_date in month_date_range:
                count_query_month = """INSERT INTO stat_referer (aggr_type, date, tour_id, referer_host, iframe, count)
                                       (
                                            SELECT 
                                                'month'::count_type, 
                                                date_trunc('month', date :month_date),
                                                tour_id, referer_host, iframe, sum(count) 
                                            FROM stat_referer 
                                            WHERE aggr_type='day'
                                                AND date between date_trunc('month', date :month_date ) 
                                                AND date_trunc('month', date :month_date) + interval '1 month' {stat_referer_filter} 
                                            GROUP BY date_trunc('month', date :month_date), tour_id, referer_host, iframe
                                       )
                                    ;""".format(**aggregate_filter)

                db.session.execute(count_query_month, {
                    'month_date': month_date.strftime('%Y-%m-%d'),
                    'tour_ids': tour_ids
                })

            for year in list(set(x.year for x in month_date_range)):
                count_query_year = """INSERT INTO stat_referer (aggr_type, date, tour_id, referer_host, iframe, count)
                                       (
                                            SELECT 
                                                'year'::count_type, 
                                                date_trunc('year', DATE :year_date),
                                                tour_id, referer_host, iframe, sum(count) 
                                            FROM stat_referer 
                                            WHERE aggr_type='month' 
                                                AND date between DATE :year_date 
                                                AND DATE :end_date {stat_referer_filter} 
                                            GROUP BY date_trunc('year', DATE :year_date), tour_id, referer_host, iframe
                                       )
                                   ;""".format(**aggregate_filter)

                db.session.execute(count_query_year, {
                    'year_date': datetime(year, 1, 1).strftime('%Y-%m-%d'),
                    'end_date': end_date,
                    'tour_ids': tour_ids,
                })

        db.session.commit()

    @classmethod
    def update_time(cls, tour_ids=[]):
        session_time_start = datetime(year=2017, month=9, day=21)

        time_query = db.session.query(StatSession.tour_id, db.func.array_agg(StatSession.time_in_session)). \
            filter(StatSession.start >= session_time_start).group_by(StatSession.tour_id)

        if tour_ids:
            AggregateTime.query.filter(AggregateTime.tour_id.in_(tour_ids)).delete(synchronize_session=False)
            time_query = time_query.filter(StatSession.tour_id.in_(tour_ids))
        else:
            db.session.execute("TRUNCATE stat_time;")

        for tour_id, timedelta_list in time_query.all():
            timedelta_json = {}
            sorted_list = sorted(timedelta_list)
            min_timedelta = None
            max_timedelta = sorted_list[-1]
            mid_timedelta = median(sorted_list)
            for delta in sorted_list:
                if not min_timedelta and delta != timedelta(seconds=0):
                    min_timedelta = delta
                if delta == timedelta(seconds=0):
                    timedelta_json[0] = timedelta_json.get(0, 0) + 1
                else:
                    for interval in [10, 60, 300, 600, 1800, 3600]:
                        if delta < timedelta(seconds=interval):
                            timedelta_json[str(interval)] = timedelta_json.get(str(interval), 0) + 1
                            break
                    if delta >= timedelta(seconds=3600):
                        timedelta_json['+3600'] = timedelta_json.get('+3600', 0) + 1
            db.session.add(AggregateTime(tour_id=tour_id,
                                         min=min_timedelta or timedelta(seconds=0),
                                         max=max_timedelta,
                                         mid=mid_timedelta,
                                         count_json=timedelta_json))


class StatUpdate:
    """Обновляет статистику в агрегационных таблицах из stat_sessions. Запускается периодически."""
    def run(self, updated_tables):
        self.log = logging.getLogger('statistics')

        try:
            fh = open(LOCK_FILE, 'x')
            fh.close()
        except FileExistsError:
            self.log.error('StatUpdate({}) завершён по причине наличия lock-файла {}'.format(updated_tables, LOCK_FILE))
            quit()

        self.log.debug('StatUpdate({})'.format(updated_tables))
        start = datetime.now()

        last_update_dates = {}
        for date in LastAggregateDate.query.all():
            last_update_dates[date.aggregate_table] = date.date_aggregate

        for table_name in updated_tables:
            name_in_db = 'stat_{}'.format(table_name)
            if name_in_db in last_update_dates:
                self.update(name_in_db, last_update_dates[name_in_db])
            else:
                self.log.error('Last updated date not found for table "stat_{}". Run: "./py.py stat-aggregate" to '
                               'aggregate statistics.'.format(table_name))

        db.session.commit()
        finish = datetime.now() - start

        if finish.seconds > current_app.config['MAX_TIME_STAT_UPDATE']:
            self.log.warning("StatUpdate работал слишком долго: {} сек!".format(finish.seconds))
            send_email(
                subject="Time update statistics {} sec!".format(finish.seconds),
                recipients=current_app.config['MAIL_STATISTIC_ERRORS'],
                html_body="Time update statistics {} sec!".format(finish.seconds)
            )
        else:
            self.log.debug("StatUpdate отработал за {} сек".format(finish.seconds))

        if os.path.isfile(LOCK_FILE):
            os.unlink(LOCK_FILE)

    def update(self, table_name, start_date):
        self.log.debug('StatUpdate.update({}, {})'.format(table_name, start_date))
        finish_date = datetime.now()
        LastAggregateDate.query.filter(LastAggregateDate.aggregate_table == table_name).update({'date_aggregate': datetime.now()})
        if table_name == 'stat_time':
            StatAggregate.update_time()
        if table_name == 'stat_count':
            self.update_count(start_date, finish_date)
        if table_name == 'stat_city':
            self.update_city(start_date, finish_date)
        if table_name == 'stat_referer':
            self.update_referer(start_date, finish_date)

    def truncate_timestamp(self, time):
        """Возвращает tuple с временем из time (типа datetime), обрезанного до часа, дня, месяца, года"""
        stat_hour = time.replace(minute=0, second=0, microsecond=0)  # Час    YYYY-MM-DD HH:00:00
        stat_day = stat_hour.replace(hour=0)  # День   YYYY-MM-DD 00:00:00
        stat_month = stat_day.replace(day=1)  # Месяц  YYYY-MM-01 00:00:00
        stat_year = stat_month.replace(month=1)  # Год    YYYY-01-01 00:00:00
        return tuple([str(_) for _ in (stat_hour, stat_day, stat_month, stat_year)])

    def update_count(self, start_date, finish_date):
        """Агрегирует статистику по хитам и уникам из stat_sessions межу start_date и finish_date."""
        self.log.debug('Агрегируются данные из сессий')
        query = """SELECT 
                        date_trunc('hour', start at time zone 'UTC') at time zone 'UTC', 
                        tour_id, count(is_uniq), count(DISTINCT session_key)
                   FROM stat_sessions
                   WHERE start >= :start_date AND start < :finish_date
                   GROUP BY date_trunc('hour', start at time zone 'UTC'), tour_id"""

        # Сюда собирается агрегированная стата по часам, дням, месяцам, годам:
        # Потом для каждого типа агрегации нужно будет сделать INSERT или UPDATE hosts += hosts в таблицу stat_count
        aggregated = {}
        tours_hits = {}
        for date, tour_id, uniq_count, session_count in db.session.execute(query, {'start_date': start_date, 'finish_date': finish_date}):
            stat_hour, stat_day, stat_month, stat_year = self.truncate_timestamp(date)

            aggregated.setdefault(tour_id, {'hour': {}, 'day': {}, 'month': {}, 'year': {}})

            aggregated[tour_id]['hour'][stat_hour] = {'hosts': uniq_count, 'hits': session_count}

            aggregated[tour_id]['day'].setdefault(stat_day, {'hosts': 0, 'hits': 0})
            aggregated[tour_id]['day'][stat_day]['hosts'] += uniq_count
            aggregated[tour_id]['day'][stat_day]['hits'] += session_count

            aggregated[tour_id]['month'].setdefault(stat_month, {'hosts': 0, 'hits': 0})
            aggregated[tour_id]['month'][stat_month]['hosts'] += uniq_count
            aggregated[tour_id]['month'][stat_month]['hits'] += session_count

            aggregated[tour_id]['year'].setdefault(stat_year, {'hosts': 0, 'hits': 0})
            aggregated[tour_id]['year'][stat_year]['hosts'] += uniq_count
            aggregated[tour_id]['year'][stat_year]['hits'] += session_count

            tours_hits.setdefault(tour_id, {'hits': 0})
            tours_hits[tour_id]['hits'] += session_count

        self.log.debug('UPSERT в stat_count, {} туров'.format(len(aggregated)))
        for tour_id, stat in aggregated.items():
            sql = """
                ALTER TABLE tours DISABLE TRIGGER set_timestamp;
                UPDATE tours SET
                    traffic_today = traffic_today + :hits,
                    traffic_total = traffic_total + :hits
                WHERE id = :tour_id;
                ALTER TABLE tours ENABLE TRIGGER set_timestamp;
            """
            db.session.execute(sql, {'tour_id': tour_id, 'hits': tours_hits[tour_id]['hits']})

            for aggr_type, counters in stat.items():
                for date, counter in counters.items():
                    sql = """
                        INSERT INTO stat_count AS sc (tour_id, aggr_type, date, count_uuids, count_sessions) 
                        VALUES (:tour_id, :aggr_type, :date, :hosts, :hits)
                        ON CONFLICT (tour_id, aggr_type, date) DO UPDATE
                            SET count_uuids = sc.count_uuids + :hosts, count_sessions = sc.count_sessions + :hits
                    """
                    params = {
                        'tour_id': tour_id,
                        'aggr_type': aggr_type,
                        'date': date,
                        'hosts': counter['hosts'],
                        'hits': counter['hits']
                    }
                    db.session.execute(sql, params)

    def update_city(self, start_date, finish_date):
        self.log.debug('Агрегируются данные из сессий')
        query = """SELECT 
                        date_trunc('day', start at time zone 'UTC') at time zone 'UTC', 
                        tour_id, city_id, count(DISTINCT session_key)
                   FROM stat_sessions
                   WHERE start >= :start_date AND start < :finish_date AND city_id IS NOT NULL
                   GROUP BY date_trunc('day', start at time zone 'UTC'), tour_id, city_id;"""

        # 'day': { tour_id: { date: { city_id: count, ... }, ... }, ... }, ... }
        aggregated = {'day': {}, 'month': {}, 'year': {}}
        for date, tour_id, city_id, session_count in db.session.execute(query, {'start_date': start_date, 'finish_date': finish_date}):
            _, stat_day, stat_month, stat_year = self.truncate_timestamp(date)

            aggregated['day'].setdefault(tour_id, {}).setdefault(stat_day, {}).setdefault(city_id, 0)
            aggregated['day'][tour_id][stat_day][city_id] += session_count

            aggregated['month'].setdefault(tour_id, {}).setdefault(stat_month, {}).setdefault(city_id, 0)
            aggregated['month'][tour_id][stat_month][city_id] += session_count

            aggregated['year'].setdefault(tour_id, {}).setdefault(stat_year, {}).setdefault(city_id, 0)
            aggregated['year'][tour_id][stat_year][city_id] += session_count

        for aggr_type, stat in aggregated.items():
            self.log.debug('UPSERT в stat_city, aggr_type={}, туров {} шт'.format(aggr_type, len(stat)))
            for tour_id, dates in stat.items():
                for date, counter in dates.items():
                    for city_id, count in counter.items():
                        sql = """
                            INSERT INTO stat_city AS sc (tour_id, aggr_type, date, city_id, count) 
                            VALUES (:tour_id, :aggr_type, :date, :city_id, :count)
                            ON CONFLICT (tour_id, aggr_type, date, city_id) DO UPDATE
                                SET count = sc.count + :count
                        """
                        params = {
                            'tour_id': tour_id,
                            'aggr_type': aggr_type,
                            'date': date,
                            'city_id': city_id,
                            'count': count
                        }
                        db.session.execute(sql, params)

    def update_referer(self, start_date, finish_date):
        query = """SELECT 
                       date_trunc('hour', start at time zone 'UTC') at time zone 'UTC', 
                       tour_id, referer_host, iframe, count(DISTINCT session_key)
                   FROM stat_sessions
                   WHERE start >= :start_date AND start < :finish_date
                   GROUP BY date_trunc('hour', start at time zone 'UTC'), tour_id, referer_host, iframe;"""

        new_sessions = {}
        date_set = set()
        for date, tour_id, referer_host, iframe, session_count in db.session.execute(query, {'start_date': start_date,
                                                                                             'finish_date': finish_date}):
            key = '{}|{}|{}'.format(tour_id, referer_host, iframe)
            if key not in new_sessions:
                new_sessions[key] = {}

            hour_now = date.replace(minute=0, second=0, microsecond=0)
            today = hour_now.replace(hour=3)
            month_now = today.replace(day=1)
            year_now = month_now.replace(month=1)
            date_set = date_set | {hour_now, today, month_now, year_now}

            for type, date_key in [('hour', hour_now), ('day', today), ('month', month_now), ('year', year_now)]:
                new_sessions[key]['{}_{}'.format(type, date_key)] = new_sessions[key].get(date_key, 0) + session_count

        if new_sessions:
            old_sessions = {}
            tours_id = ', '.join([key.split('|')[0] for key in new_sessions.keys()])
            date_list = ', '.join(["'{}'".format(date) for date in date_set])
            query = """SELECT aggr_type, date, tour_id, referer_host, iframe, count FROM stat_referer
                       WHERE tour_id in ({}) and date in ({})""".format(tours_id, date_list)
            for sessions in db.session.execute(query):
                key = '{}|{}|{}'.format(sessions[2], sessions[3], sessions[4])
                if key not in old_sessions:
                    old_sessions[key] = {}
                old_sessions[key]['{}_{}'.format(sessions[0], sessions[1])] = sessions

            for key in new_sessions.keys():
                for date_key in new_sessions[key].keys():
                    if date_key not in old_sessions.get(key, []):
                        tour_id, referer_host, iframe = key.split('|')
                        aggr_type, date = date_key.split('_')
                        db.session.add(AggregateReferer(aggr_type=aggr_type,
                                                        date=datetime.strptime(date[:-3] + date[-2:], '%Y-%m-%d %H:%M:%S%z'),
                                                        tour_id=tour_id,
                                                        referer_host=None if referer_host == 'None' else referer_host,
                                                        iframe=iframe == 'True',
                                                        count=new_sessions[key].get(date_key, 0)))
                    else:
                        session = old_sessions[key][date_key]
                        AggregateReferer.query.filter(AggregateReferer.aggr_type == session[0],
                                                      AggregateReferer.date == session[1],
                                                      AggregateReferer.tour_id == session[2],
                                                      AggregateReferer.referer_host == session[3],
                                                      AggregateReferer.iframe == session[4]).\
                            update({'count': session[5] + new_sessions[key].get(date_key, 0)})


class StatDelete:
    """Удаляет старую статистику из агрегационных таблиц. Запускается периодически."""
    def run(self):
        self.log = logging.getLogger('statistics')
        params = {'history_depth_hours': '{} day'.format(current_app.config['HISTORY_DEPTH_HOURS']),
                  'history_depth_days': '{} year'.format(current_app.config['HISTORY_DEPTH_DAYS']),
                  'history_depth_months': '{} year'.format(current_app.config['HISTORY_DEPTH_MONTHS']),
                  'history_depth_years': '{} year'.format(current_app.config['HISTORY_DEPTH_YEARS'])}
        for table_name in ['stat_count ', 'stat_city', 'stat_referer']:
            query = """DELETE FROM {}
                       WHERE (aggr_type = 'hour' AND date < now() - INTERVAL :history_depth_hours)
                       OR (aggr_type = 'day' AND date < now() - INTERVAL :history_depth_days)
                       OR (aggr_type = 'month' AND date < now() - INTERVAL :history_depth_months)
                       OR (aggr_type = 'year' AND date < now() - INTERVAL :history_depth_years);""".format(table_name)
            self.log.debug('StatDelete {}'.format(table_name))
            db.session.execute(query, params)

        self.log.debug('StatDelete stat_sessions')
        StatSession.query\
            .filter(StatSession.start < db.func.now() - db.text("INTERVAL '{}'".format(current_app.config['HISTORY_DEPTH_SESSIONS'])))\
            .delete(synchronize_session=False)

        db.session.commit()


class StatRecount:
    """Обнуляет и обновляет статистику в Tour.traffic_* из значений в StatCount"""
    def run(self):
        self.log = logging.getLogger('statistics')
        self.log.debug('StatRecount()')

        query = """
            SELECT tour_id, 
                (SELECT sum(count_sessions) 
                FROM stat_count 
                WHERE aggr_type='hour' AND date_trunc('day', date)=current_date AND tour_id=sc.tour_id) 
            AS traffic_today, sum(count_sessions) AS traffic_total 
            FROM stat_count as sc WHERE aggr_type='month' GROUP BY tour_id;
        """

        for tour_id, traffic_today, traffic_total in db.session.execute(query):
            sql = """
                ALTER TABLE tours DISABLE TRIGGER set_timestamp;
                UPDATE tours SET
                    traffic_today = :traffic_today,
                    traffic_total = :traffic_total
                WHERE id = :tour_id;
                ALTER TABLE tours ENABLE TRIGGER set_timestamp;
            """
            db.session.execute(sql, {'tour_id': tour_id,
                                     'traffic_today': traffic_today or 0,
                                     'traffic_total': traffic_total or 0
                             })
        db.session.commit()


class StatZero:
    """Обнуляет статистику в Tour.traffic_today"""
    def run(self):
        self.log = logging.getLogger('statistics')
        self.log.debug('StatZero()')

        query = """
            ALTER TABLE tours DISABLE TRIGGER set_timestamp;
            UPDATE tours SET traffic_today=0;
            ALTER TABLE tours ENABLE TRIGGER set_timestamp;
        """
        db.session.execute(query)
        db.session.commit()
