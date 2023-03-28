from pytz import timezone
from random import randrange
from datetime import datetime, timedelta

from numpy.random import choice
from flask import current_app
from flask_babel import Babel, get_timezone
from flask_login import login_user, logout_user, current_user

from visual.models import Tour, User, StatSession
from visual.core import db
from manage.stat_aggregate import StatAggregate
from .progress import Progress


class StatDemo:
    """Генерирует фейковую статистику для пользователя (использовать для демо-аккаунта)"""
    def run(self, user_email, from_date, to_date, quiet=False):
        _from_date = from_date
        _to_date = to_date

        def apply_date_bounds(model, query):
            """Применяет к query класса model фильтры по дате
            """
            if from_date:
                query = query.filter(model.start >= from_date)
            if to_date:
                query = query.filter(model.start <= to_date)
            return query

        def get_date_param(param, interval_type):
            """Читает дату из параметра --from-date, --to-date, ставит дефолтное значение
            """
            if param is not None:
                try:
                    param = datetime.strptime(param, '%Y-%m-%d').replace(tzinfo=timezone(user.timezone or 'Etc/GMT+0'))
                    if interval_type == 'to':
                        param = param.replace(hour=23, minute=59, second=59, microsecond=59)
                except (TypeError, ValueError):
                    current_app.logger.warning('Не верный формат {}'.format(param))
                    exit()
            else:
                param = datetime.utcnow().replace(minute=0, second=0, microsecond=0, tzinfo=timezone(user.timezone  or 'Etc/GMT+0'))
                if interval_type == 'to':
                    param = param + timedelta(hours=1)

            return param

        def get_random_value(values_dict):
            weight_sum = sum(values_dict.values())
            weight = [value/weight_sum for value in values_dict.values()]
            return choice(list(values_dict.keys()), 1, p=weight)[0]

        def get_traffic_range(property, traffic_date):
            days_coef = property['days_coef'][traffic_date.weekday()]
            min_traffic, max_traffic = property['hours_coef'][traffic_date.hour]
            if max_traffic == 0:
                return []
            return range(int(days_coef*randrange(min_traffic, max_traffic)))

        user = User.query.filter(db.func.lower(User.email) == user_email.lower()).first()

        if not user:
            current_app.logger.warning('Пользователь с почтой {} не найден'.format(user_email))
            return

        from_date = get_date_param(from_date, 'from')
        to_date = get_date_param(to_date, 'to')

        if from_date > to_date:
            current_app.logger.warning('Дата начала позже чем дата конца')
            return

        if not quiet:
            date_interval = '{:%Y-%m-%d %H:%M} - {:%Y-%m-%d %H:%M}'.format(from_date, to_date)
            current_app.logger.info('Генерируем статистику для пользователя {} на {}'.format(user.email, date_interval))

        tour_ids = db.session.query(Tour.id).filter(Tour.user_id == user.id).all()
        tour_ids = [str(x[0]) for x in tour_ids]

        # Стираем фейковую статистику за заданный период
        query = StatSession.query.filter(StatSession.tour_id.in_(tour_ids))
        query = apply_date_bounds(StatSession, query)
        query.delete(synchronize_session=False)

        db.session.commit()

        tours_properties = [{'referer_host': {'biganto.com': 10,
                                             'www.bnpparibas.immo': 7,
                                             '': 2,
                                             'belvederpark.ru': 3,
                                             'logement.bnpparibas.fr': 5,
                                             'designmira.ru': 1,
                                             'influence-immo.fr': 6,
                                             'interior-design.moscow': 4,
                                             'image.baidu.com': 1,
                                             'm.facebook.com': 1,
                                             'away.vk.com': 2,
                                             'www.jacquet-investissement.fr': 4
                                             },
                            'city': {524901: 3,
                                     2988507: 10,
                                     5375480: 0.5,
                                     2861096: 3.1,
                                     498817: 2,
                                     2017370: 3,
                                     2867714: 3.8,
                                     294640: 1,
                                     5808079: 1,
                                     2921044: 4,
                                     4744870: 0.8,
                                     2977824: 5},
                            'time': {0: 0.05,
                                     35: 0.25,
                                     180: 0.4,
                                     450: 0.2,
                                     1200: 0.1,
                                     2700: 0.05,
                                     5400: 0.05},
                            'days_coef': {0: 0.75,      # Понедельник
                                          1: 0.6,
                                          2: 0.6,
                                          3: 0.8,
                                          4: 0.6,
                                          5: 0.6,
                                          6: 0.85},     # Воскресенье
                            'hours_coef': {0: (0, 0),   # Полночь по UTC
                                           1: (0, 1),
                                           2: (0, 1),
                                           3: (0, 0),
                                           4: (0, 0),
                                           5: (0, 0),
                                           6: (0, 1),
                                           7: (0, 1),
                                           8: (0, 2),
                                           9: (0, 3),
                                           10: (1, 3),
                                           11: (1, 4),  # От 0 до 3 посетителей
                                           12: (2, 4),  # Полдень по UTC
                                           13: (3, 5),
                                           14: (2, 5),
                                           15: (1, 3),
                                           16: (1, 3),
                                           17: (1, 4),
                                           18: (3, 5),
                                           19: (2, 4),
                                           20: (1, 4),
                                           21: (1, 3),
                                           22: (0, 2),
                                           23: (0, 1)
                                           },
                            },
                            {'referer_host': {'biganto.com': 5,
                                             'tushino2018.ru': 10,
                                             '': 2,
                                             'ww-realty.ru': 1,
                                             'biganto.ru': 0.07,
                                             'yandex.ru': 2,
                                             'www.google.com': 3,
                                             'm.facebook.com': 0.5,
                                             'away.vk.com': 1,
                                             },
                            'city': {524901: 10,
                                     2988507: 0.5,
                                     5375480: 1,
                                     3017382: 0.07,
                                     2861096: 0.1,
                                     498817: 7,
                                     2017370: 4,
                                     2867714: 1,
                                     294640: 0.05,
                                     2921044: 1,
                                     5808079: 1,
                                     523812: 8,
                                     550280: 6},
                            'time': {0: 0.1,
                                     35: 0.2,
                                     180: 0.4,
                                     450: 0.3,
                                     1200: 0.1,
                                     2700: 0.05,
                                     5400: 0.1},
                            'days_coef': {0: 0.6,      # Понедельник
                                          1: 0.5,
                                          2: 0.5,
                                          3: 0.5,
                                          4: 0.5,
                                          5: 0.9,
                                          6: 0.8},     # Воскресенье
                            'hours_coef': {0: (0, 1),   # Полночь по UTC
                                           1: (0, 1),
                                           2: (0, 0),
                                           3: (0, 0),
                                           4: (0, 2),
                                           5: (1, 3),
                                           6: (2, 5),
                                           7: (3, 6),
                                           8: (4, 7),
                                           9: (4, 7),
                                           10: (5, 6),
                                           11: (4, 5),  # От 0 до 3 посетителей
                                           12: (3, 5),  # Полдень по UTC
                                           13: (3, 5),
                                           14: (4, 6),
                                           15: (4, 7),
                                           16: (4, 7),
                                           17: (1, 5),
                                           18: (2, 6),
                                           19: (1, 3),
                                           20: (0, 2),
                                           21: (0, 1),
                                           22: (0, 0),
                                           23: (0, 0)}
                            },
                            {'referer_host': {'biganto.com': 5,
                                             'www.radisson-cruise.ru': 10,
                                             '': 3,
                                             'm.facebook.com': 1,
                                             'away.vk.com': 2},
                            'city': {524901: 10,
                                     2988507: 2,
                                     5375480: 0.8,
                                     3017382: 0.8,
                                     2861096: 0.8,
                                     498817: 7,
                                     2017370: 8,
                                     2867714: 1,
                                     294640: 0.5,
                                     2921044: 2,
                                     5808079: 1.5,
                                     523812: 5,
                                     550280: 4.5},
                            'time': {0: 0.01,
                                     35: 0.2,
                                     180: 0.4,
                                     450: 0.4,
                                     1200: 0.1,
                                     2700: 0.05},
                            'days_coef': {0: 0.7,  # Понедельник
                                          1: 0.7,
                                          2: 0.7,
                                          3: 0.7,
                                          4: 0.7,
                                          5: 0.9,
                                          6: 0.9},  # Воскресенье
                            'hours_coef': {0: (0, 1),  # Полночь по UTC
                                           1: (0, 1),
                                           2: (0, 0),
                                           3: (0, 0),
                                           4: (0, 1),
                                           5: (0, 2),
                                           6: (1, 4),
                                           7: (1, 4),
                                           8: (2, 5),
                                           9: (2, 5),
                                           10: (1, 4),
                                           11: (1, 4),  # От 0 до 3 посетителей
                                           12: (1, 3),  # Полдень по UTC
                                           13: (1, 4),
                                           14: (2, 4),
                                           15: (2, 5),
                                           16: (2, 5),
                                           17: (0, 4),
                                           18: (1, 4),
                                           19: (0, 2),
                                           20: (0, 1),
                                           21: (0, 0),
                                           22: (0, 0),
                                           23: (0, 0)}
                            },
                            {'referer_host': {'biganto.com': 7,
                                             'straubing.biganto.com': 3,
                                             '': 1,
                                             'resalestraubing.de': 10,
                                             'm.facebook.com': 0.5},
                            'city': {524901: 2,
                                     2988507: 3,
                                     3017382: 1,
                                     2861096: 10,
                                     498817: 1,
                                     2017370: 0.5,
                                     2867714: 6,
                                     294640: 0.1,
                                     2921044: 8},
                            'time': {0: 0.1,
                                     35: 0.3,
                                     180: 0.5,
                                     450: 0.2,
                                     1200: 0.1,
                                     2700: 0.1,
                                     5400: 0.1},
                            'days_coef': {0: 0.75,      # Понедельник
                                          1: 0.6,
                                          2: 0.6,
                                          3: 0.6,
                                          4: 0.6,
                                          5: 0.75,
                                          6: 0.85},     # Воскресенье
                            'hours_coef': {0: (0, 0),   # Полночь по UTC
                                           1: (0, 1),
                                           2: (0, 1),
                                           3: (0, 0),
                                           4: (0, 0),
                                           5: (0, 1),
                                           6: (0, 2),
                                           7: (0, 2),
                                           8: (0, 3),
                                           9: (0, 4),
                                           10: (1, 5),
                                           11: (1, 5),  # От 0 до 3 посетителей
                                           12: (2, 4),  # Полдень по UTC
                                           13: (2, 4),
                                           14: (2, 3),
                                           15: (1, 5),
                                           16: (1, 5),
                                           17: (1, 4),
                                           18: (2, 4),
                                           19: (2, 3),
                                           20: (1, 3),
                                           21: (1, 2),
                                           22: (0, 1),
                                           23: (0, 0)
                                           },
                            },
                            {'referer_host': {'biganto.com': 5,
                                             'image.baidu.com': 1,
                                             '': 0.25,
                                             'www.google.com': 2},
                            'city': {524901: 2,
                                     2988507: 0.05,
                                     5375480: 0.5,
                                     498817: 0.3,
                                     2017370: 7,
                                     294640: 5,
                                     5808079: 2,
                                     4744870: 0.5},
                            'time': {0: 0.05,
                                     35: 0.2,
                                     180: 0.5,
                                     450: 0.3,
                                     1200: 0.2,
                                     2700: 0.1,
                                     5400: 0.1},
                            'days_coef': {0: 0.6,      # Понедельник
                                          1: 0.6,
                                          2: 0.7,
                                          3: 0.7,
                                          4: 0.8,
                                          5: 0.8,
                                          6: 0.85},     # Воскресенье
                            'hours_coef': {0: (0, 0),   # Полночь по UTC
                                           1: (0, 1),
                                           2: (0, 1),
                                           3: (0, 0),
                                           4: (0, 0),
                                           5: (0, 0),
                                           6: (0, 1),
                                           7: (0, 1),
                                           8: (0, 2),
                                           9: (0, 2),
                                           10: (1, 3),
                                           11: (1, 3),  # От 0 до 3 посетителей
                                           12: (2, 4),  # Полдень по UTC
                                           13: (2, 4),
                                           14: (2, 4),
                                           15: (1, 3),
                                           16: (1, 3),
                                           17: (1, 4),
                                           18: (2, 4),
                                           19: (2, 4),
                                           20: (1, 4),
                                           21: (1, 3),
                                           22: (0, 2),
                                           23: (0, 1)
                                           }
                            }]
        if not quiet:
            progress = Progress()
            progress.action('Генерируем статистику туров', len(tour_ids))
        for index, tour_id in enumerate(tour_ids):
            if not quiet:
                progress.step()

            count_hours = int((to_date - from_date).total_seconds()/3600)
            property_key = int(index*len(tours_properties)/len(tour_ids))
            property = tours_properties[property_key]
            for hour in range(count_hours):
                tour_start_time = from_date + timedelta(hours=hour)
                for _ in get_traffic_range(property, tour_start_time):
                    db.session.add(StatSession(tour_id=tour_id,
                                               session_key=StatSession.generate_key(),
                                               start=tour_start_time,
                                               time_in_session=timedelta(seconds=int(get_random_value(property['time']))),
                                               ip='127.0.0.1',
                                               city_id=int(get_random_value(property['city'])),
                                               referer_host=get_random_value(property['referer_host']),
                                               iframe=True if randrange(10) == 5 else False,
                                               is_uniq=True if randrange(10) <= 7 else None))

            db.session.commit()

        tour_ids_parameter = ','.join(tour_ids)

        StatAggregate().run(updated_tables=['count', 'time', 'city', 'referer'], tour_ids=tour_ids_parameter,
                            interval=_from_date + '...' + _to_date)

        if not quiet:
            progress.end()
