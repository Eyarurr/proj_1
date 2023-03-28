import re, os, gzip, uuid, sys
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import urlparse

import requests
import numpy
import pandas
from flask import current_app
from flask_script import Command, Option
from geoip2.database import Reader
from geoip2.errors import AddressNotFoundError

from visual.models import StatSession, Tour
from visual.core import db


class SaveSessions(Command):
    def __init__(self, func=None):
        super().__init__(func)

    def run(self):
        StatSession.save_session_to_db()


class StatImportNginxLogs(Command):
    """Импортирует статистику из логов nginx"""
    ARCHIVE_URL = 'http://geolite.maxmind.com/download/geoip/database/GeoLite2-City.mmdb.gz'

    option_list = (
        Option('log_file'),
    )

    def __init__(self, func=None):
        super().__init__(func)

    def run(self, log_file):
        self.geo_db = self.init_geo_db()
        current_app.stat_logger.info('start loading log file')
        data = self.load_data(log_file)
        current_app.stat_logger.info('tranform data to session')
        session_dict = self.get_session_dict(data)
        current_app.stat_logger.info('save sessions in db')
        self.save_in_db(session_dict)

    @classmethod
    def init_geo_db(cls):
        try:
            os.remove('var/geo_data/GeoLite2-City.mmdb')
        except (OSError, IOError):
            pass
        with open('var/geo_data/GeoLite2-City.mmdb', 'wb') as archive:
            archive.write(cls.get_archive().read())

    @classmethod
    def get_archive(cls):
        archive = requests.get(cls.ARCHIVE_URL, stream=True)
        if archive.status_code != 200:
            current_app.stat_logger.error("dev.maxmind.com status: {}".format(archive.status_code))
        return gzip.GzipFile(fileobj=BytesIO(archive.content))

    @classmethod
    def parse_datetime(cls, time):
        try:
            dt = datetime.strptime(time[1:], '%d/%b/%Y:%H:%M:%S')
        except ValueError:
            return ''
        else:
            return dt

    @classmethod
    def return_value_by_template(cls, request, template):
        try:
            value_redexp = re.search(template, request)
            return value_redexp.group('value')
        except:
            return ''

    @classmethod
    def load_data(cls, log_file):
        data = pandas.read_csv(log_file,
                               delimiter=" ",
                               na_values='-',
                               header=None,
                               usecols=[0, 3, 5, 8, 9],
                               names=['ip', 'time', 'request', 'referer', 'user_agent'])

        current_app.stat_logger.info("Log data count: {}".format(data['ip'].count()))

        start_log_date = data['time'].iloc[0]
        finish_log_date = data['time'].iloc[-1]
        current_app.stat_logger.info("Log date: {} - {}".format(start_log_date, finish_log_date))

        data['tour_id'] = data.apply(lambda row: cls.return_value_by_template(row['request'], 'GET /tour/(?P<value>\d+)'), axis=1)

        tour_ids = (str(tour.id) for tour in db.session.query(Tour).all())
        data = data[data.tour_id != '']
        data = data[data['tour_id'].isin(tour_ids)]

        current_app.stat_logger.info("Log tour data count: {}".format(data['tour_id'].count()))

        for key in ['offer_id', 'iframe']:
            data[key] = data.apply(lambda row: cls.return_value_by_template(row['request'], '{}=(?P<value>\d+)'.format(key)), axis=1)

        data['uuid'] = data.apply(lambda row: uuid.uuid3(uuid.NAMESPACE_DNS, str(row['ip']) + str(row['user_agent'])), axis=1)
        data['time'] = data.apply(lambda row: cls.parse_datetime(row['time']), axis=1)

        current_app.stat_logger.info("Log data clear old statistics")

        del data['request']
        StatSession.clear_db_statistic(start_log_date, finish_log_date)

        current_app.stat_logger.info("Replace Nan to None")

        data = pandas.DataFrame(data).replace({numpy.nan: ''})

        return data.to_dict(orient='index')

    @classmethod
    def get_city(cls, ip, ip_geo_db):
        try:
            response = ip_geo_db.city(ip)
            return response.city.geoname_id
        except AddressNotFoundError:
            return None

    @classmethod
    def get_session_dict(cls, data):

        ip_geo_db = Reader('var/geo_data/GeoLite2-City.mmdb')

        session_keys = {}
        sessions_statistics = {}

        for session in sorted(data.values(), key=lambda k: k['time']):
            session_key = session_keys.get(session['uuid'], {'key': uuid.uuid4(),
                                                             'time': session['time'] + timedelta(minutes=30)})
            if session_key['time'] < session['time']:
                session_key['key'] = uuid.uuid4()
            session_key['time'] = session['time'] + timedelta(minutes=30)
            session_keys[session['uuid']] = session_key

            key = '{}.{}'.format(session['tour_id'], session_key['key'])
            instance = sessions_statistics.get(key, None)
            if instance is None:
                offer_id = session.get('offer_id', '')
                tour_id = session.get('tour_id', '')
                referer = urlparse(session.get('referer', ''))
                sessions_statistics[key] = {'session_key': session_key['key'],
                                            'start': StatSession.set_datetime(session['time']),
                                            'time_in_session': 0,
                                            'ip': session['ip'],
                                            'city_id': cls.get_city(session['ip'], ip_geo_db),
                                            'referer_host': referer.netloc if referer.netloc != '' else None,
                                            'referer_path': referer.path if referer.path != '' else None,
                                            'referer_query_string': referer.query if referer.query != '' else None,
                                            'iframe': session['iframe'] == '1',
                                            'is_uniq': True,
                                            'offer_id': int(offer_id) if offer_id != '' else None,
                                            'tour_id': int(tour_id) if tour_id != '' else None,
                                            'user_agent': session['user_agent']}
            else:
                time_start = StatSession.get_datetime(sessions_statistics[key]['start'])
                sessions_statistics[key]['time_in_session'] = (session['time'] - time_start).total_seconds()

        return sessions_statistics

    @classmethod
    def save_in_db(cls, sessions_dict):
        for session in (StatSession.stat_from_dict(sessions_dict[key]) for key in sessions_dict.keys()):
            db.session.add(session)
        db.session.commit()
