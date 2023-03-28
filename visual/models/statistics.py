import logging
import user_agents
import uuid, datetime, json
from urllib.parse import urlparse

from sqlalchemy.dialects.postgresql import UUID, CHAR, TIMESTAMP, INET, JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from flask import request, make_response, current_app, url_for
from redis.exceptions import ConnectionError

from visual.core import db, redis
from visual.util import get_lang, defer_cookie


AGGR_TYPES = {
    'hour': 'По часам',
    'day': 'По дням',
    'month': 'По месяцам',
    'year': 'По годам'
}


class Country(db.Model):
    __tablename__ = 'countries'

    id = db.Column(CHAR(2), primary_key=True)
    name_ru = db.Column(db.String(100))
    name_en = db.Column(db.String(100))
    name_de = db.Column(db.String(100))
    name_fr = db.Column(db.String(100))
    city = db.relationship('City', back_populates='country')

    @classmethod
    def get_name_field(cls):
        return getattr(cls, 'name_' + get_lang())

    @hybrid_property
    def name(self):
        return getattr(self, 'name_' + get_lang())

    @name.setter
    def name(self, value):
        setattr(self, 'name_' + get_lang(), value)


class City(db.Model):
    __tablename__ = 'cities'

    id = db.Column(db.Integer(), primary_key=True)
    name_ru = db.Column(db.String(100))
    name_en = db.Column(db.String(100))
    name_de = db.Column(db.String(100))
    name_fr = db.Column(db.String(100))
    country_id = db.Column(CHAR(2), db.ForeignKey('countries.id'), nullable=False)
    team_member = db.relationship('TeamMember', back_populates='city')
    country = db.relationship('Country', back_populates='city')

    @classmethod
    def get_name_field(cls):
        return getattr(cls, 'name_' + get_lang())

    @hybrid_property
    def name(self):
        return getattr(self, 'name_' + get_lang())

    @name.setter
    def name(self, value):
        setattr(self, 'name_' + get_lang(), value)

    def api_view(self):
        return {'id': self.id, 'country_id': self.country_id, 'name': self.name}


class StatSession(db.Model):
    __tablename__ = 'stat_sessions'

    DEVICE_PC = 1
    DEVICE_TABLET = 2
    DEVICE_MOBILE = 3

    LIFE_TIME_SESSION_MINUTES = 10
    LIFE_TIME_UNIQ_DAY = 1

    tour_id = db.Column(db.Integer,
                        db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'),
                        nullable=False,
                        primary_key=True)
    session_key = db.Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    start = db.Column(TIMESTAMP(timezone=True), server_default=db.text('now()'), nullable=False)
    time_in_session = db.Column(db.Interval, nullable=False, server_default='0')
    ip = db.Column(INET(), nullable=False)
    city_id = db.Column(db.Integer(), db.ForeignKey('cities.id', ondelete='RESTRICT', onupdate='CASCADE'))

    user_agent = db.Column(db.String(1024))
    device_type = db.Column(db.SmallInteger())
    device_brand = db.Column(db.String(255))
    device_model = db.Column(db.String(255))
    os_family = db.Column(db.String(255))
    os_version = db.Column(db.String(255))
    browser_family = db.Column(db.String(255))
    browser_version = db.Column(db.String(255))

    referer_host = db.Column(db.String(1024))
    referer_path = db.Column(db.String(2048))
    referer_query_string = db.Column(db.String(2048))

    iframe = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    offer_id = db.Column(db.Integer, db.ForeignKey('offers.id', ondelete='SET NULL', onupdate='CASCADE'))

    is_uniq = db.Column(db.Boolean, nullable=True)

    @classmethod
    def generate_key(cls):
        """Генерирует новый сессионный ключ."""
        return str(uuid.uuid4()).replace('-', '')

    def fill(self, request):
        """Заполняет свои поля из данных запроса request."""
        cls = StatSession

        self.ip = request.remote_addr

        # В uwsgi-окружении, код города приходит в request.environ, в dev - в request.headers
        self.city_id = request.headers.get('X-City', request.environ.get('X_CITY'))
        if self.city_id is not None:
            self.city_id = int(self.city_id or '0')

        self.offer_id = request.args.get('offer_id')
        self.iframe = request.args.get('iframe') == '1'

        self.is_uniq = True if request.cookies.get('u') is None else None

        referer = urlparse(request.headers.get('Referer', ''))
        self.referer_host = referer.netloc[:cls.referer_host.type.length] if referer.netloc != '' else None
        self.referer_path = referer.path[:cls.referer_path.type.length] if referer.path != '' else None
        self.referer_query_string = referer.query[:cls.referer_query_string.type.length] if referer.query != '' else None

        self.user_agent = str(request.headers.get('User-Agent'))[:cls.user_agent.type.length]
        self.parse_user_agent()

    def parse_user_agent(self):
        """
        Парсит self.user_agent и заполняет свойства device_type, device_brand, device_model,
        os_family, os_version, browser_family, browser_version.

        Если определился бот, возвращает False
        :return:
        """
        if not self.user_agent:
            return True

        ua = user_agents.parse(self.user_agent)
        if ua.is_bot:
            return False

        if ua.is_pc:
            self.device_type = self.DEVICE_PC
        elif ua.is_tablet:
            self.device_type = self.DEVICE_TABLET
        elif ua.is_mobile:
            self.device_type = self.DEVICE_MOBILE

        self.device_brand = ua.device.brand
        self.device_model = ua.device.model
        self.os_family = ua.os.family
        self.os_version = '.'.join([str(_) for _ in ua.os.version[:2]])
        self.browser_family = ua.browser.family
        self.browser_version = '.'.join([str(_) for _ in ua.browser.version[:2]])

        return True

    def prolongate(self):
        """Продлевает сессию до текущего времени."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.time_in_session = now - self.start

    def set_cookies(self):
        """Ставит куки: сессионную и про уникальность."""
        defer_cookie(
            's', str(self.session_key).replace('-', ''),
            path=url_for('front.tour', tour_id=self.tour_id),
            max_age=datetime.timedelta(minutes=StatSession.LIFE_TIME_SESSION_MINUTES)
        )
        defer_cookie(
            'u', '1',
            path=url_for('front.tour', tour_id=self.tour_id),
            max_age=datetime.timedelta(days=StatSession.LIFE_TIME_UNIQ_DAY)
        )

    # Дальше — методы и свойства, существовавшие до рефакторинга статистики.
    # @todo: выхерить неиспользуемое.

    DATE_FORMAT = "%y-%m-%d %H:%M:%S"

    @classmethod
    def get_datetime(cls, str_datetime):
        return datetime.datetime.strptime(str_datetime, cls.DATE_FORMAT)

    @classmethod
    def set_datetime(cls, datetime):
        return datetime.strftime(cls.DATE_FORMAT)

    @classmethod
    def update_session_cookies(cls, response, session_key, tour_id):
        response.set_cookie('s',
                            session_key,
                            path=url_for('front.tour', tour_id=tour_id),
                            max_age=datetime.timedelta(minutes=cls.LIFE_TIME_SESSION_MINUTES))
        response.set_cookie('u',
                            '1',
                            path=url_for('front.tour', tour_id=tour_id),
                            max_age=datetime.timedelta(days=cls.LIFE_TIME_UNIQ_DAY))
        return response

    @classmethod
    def stat_from_binary_string(cls, binary_string):
        dict_session = json.loads(binary_string.decode('utf8'))
        return cls.stat_from_dict(dict_session)

    @classmethod
    def stat_from_dict(cls, session):
        return cls(session_key=session['session_key'],
                   start=cls.get_datetime(session['start']),
                   time_in_session=datetime.timedelta(seconds=session['time_in_session']),
                   ip=session['ip'],
                   city_id=session['city_id'],
                   referer_host=session['referer_host'],
                   referer_path=session['referer_path'],
                   referer_query_string=session['referer_query_string'],
                   iframe=session['iframe'],
                   offer_id=session['offer_id'],
                   tour_id=session['tour_id'],
                   is_uniq=session['is_uniq'],
                   user_agent=session['user_agent'])

    @classmethod
    def push_session(cls, session):
        log = logging.getLogger('statistics')
        if current_app.config['USE_REDIS_IN_STATISTICS']:
            try:
                key = '{}.{}'.format(session['tour_id'], session['session_key'])
                redis.set(key, json.dumps(session))
                return
            except ConnectionError:
                log.warning("Redis connection error. Statistics add in db")
        statistic = cls.query.filter_by(session_key=session['session_key'],
                                        tour_id=session['tour_id'])
        if statistic.first() is None:
            if db.session.query(City.id).filter_by(id=session['city_id']).first() is not None:
                db.session.add(cls.stat_from_dict(session))
                try:
                    db.session.commit()
                except BaseException as e:
                    log.error("Problem in push statistics from db ({})".format(e))
                    db.session.rollback()

    @classmethod
    def save_session_to_db(cls):
        # Используется только в manage/stat_import_nginx_logs.py
        log = logging.getLogger('statistics')
        try:
            keys = [key.decode('utf8') for key in redis.keys()]
            if keys:
                dublicate = db.session.query(cls).filter(db.func.concat(cls.tour_id, '.', cls.session_key).in_(keys)).all()
                sessions_dict = {key: cls.stat_from_binary_string(redis.get(key)) for key in keys}
                for session in dublicate:
                    key = '{}.{}'.format(session.tour_id, session.session_key)
                    cls.query.filter(cls.tour_id == session.tour_id,
                                     cls.session_key == session.session_key). \
                        update({'time_in_session': cls.time_in_session + sessions_dict[key].time_in_session})
                    del sessions_dict[key]
                db.session.add_all(sessions_dict.values())
                db.session.commit()
                redis.delete(*keys)
        except BaseException as e:
            log.error("Problem in update statistics from db ({})".format(e))

    @classmethod
    def save_session(cls, session_key, tour_id, is_uniq):
        # В uwsgi-окружении, код города приходит в request.environ, в dev - в request.headers
        city_id = int(request.headers.get('X-City', 0))
        if not city_id:
            city_id = int(request.environ.get('X_CITY', 0))

        offer_id = int(request.args.get('offer_id', 0))

        time_date = datetime.datetime.now()

        referer = urlparse(request.headers.get('Referer', ''))
        referer_host = referer.netloc[:cls.referer_host.type.length] if referer.netloc != '' else None
        referer_path = referer.path[:cls.referer_path.type.length] if referer.path != '' else None
        referer_query_string = referer.query[:cls.referer_query_string.type.length] if referer.query != '' else None

        session = {'session_key': str(uuid.UUID(session_key)),
                   'start': cls.set_datetime(time_date),
                   'time_in_session': 0,
                   'ip': request.remote_addr,
                   'city_id': city_id if city_id != 0 else None,
                   'referer_host': referer_host,
                   'referer_path': referer_path,
                   'referer_query_string': referer_query_string,
                   'iframe': request.args.get('iframe') == '1',
                   'offer_id': offer_id if offer_id != 0 else None,
                   'tour_id': int(tour_id),
                   'is_uniq': True if is_uniq is None else None,
                   'user_agent': request.headers.get('User-Agent')[:cls.user_agent.type.length]}
        cls.push_session(session)

    @classmethod
    def clear_db_statistic(cls, start_log_date, finish_log_date):
        db.session.query(cls).filter(cls.start > start_log_date).filter(cls.start < finish_log_date).delete()

    @classmethod
    def wrapper(cls, rendered_template, tour_id, enabled=True):
        if not enabled:
            return rendered_template
        response = make_response(rendered_template)

        session_key = request.cookies.get('s', cls.generate_key())
        is_uniq = request.cookies.get('u', None)

        cls.save_session(session_key, tour_id, is_uniq)

        return cls.update_session_cookies(response, session_key, tour_id)

    @classmethod
    def update_session_time(cls, rendered_template, tour_id):
        session_key = request.cookies.get('s')
        if session_key is None:
            return cls.wrapper(rendered_template, tour_id)

        response = make_response(rendered_template)
        response.set_cookie('s',
                            session_key,
                            path=url_for('front.tour', tour_id=tour_id),
                            max_age=datetime.timedelta(minutes=cls.LIFE_TIME_SESSION_MINUTES))
        response.set_cookie('u',
                            '1',
                            path=url_for('front.tour', tour_id=tour_id),
                            max_age=datetime.timedelta(days=cls.LIFE_TIME_UNIQ_DAY))

        if current_app.config['USE_REDIS_IN_STATISTICS']:
            try:
                key = '{}.{}'.format(tour_id, str(uuid.UUID(session_key)))
                session = redis.get(key)
                if session is not None:
                    session = json.loads(session.decode('utf-8'))
                    session['time_in_session'] += current_app.config['PLAYER_HIT_TIME']
                    redis.set(key, json.dumps(session))
                    return response
                else:
                    return rendered_template
            except ConnectionError:
                log = logging.getLogger('statistics')
                log.warning("Redis connection error. Statistics add in db")

        statistic = cls.query.filter_by(session_key=session_key,
                                        tour_id=tour_id)

        update_time = datetime.timedelta(seconds=current_app.config['PLAYER_HIT_TIME'])
        statistic.update({'time_in_session': cls.time_in_session + update_time},
                         synchronize_session=False)
        db.session.commit()

        return response


class LastAggregateDate(db.Model):
    """Здесь хранится время, когда в последний раз агрегироваласт статистика в разные агрегационные таблицы.
    """
    __tablename__ = 'stat_date_aggregate'

    aggregate_table = db.Column(db.Enum(*['stat_count', 'stat_city', 'stat_time', 'stat_referer'], name='aggregate_tables'),
                                nullable=False, primary_key=True)
    date_aggregate = db.Column(TIMESTAMP(timezone=True),
                               nullable=False,
                               server_default=db.text('now()'))


class AggregateCount(db.Model):
    __tablename__ = 'stat_count'

    tour_id = db.Column(db.Integer,
                        db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'),
                        nullable=False, primary_key=True)
    aggr_type = db.Column(db.Enum(*list(AGGR_TYPES.keys()), name='count_type'), nullable=False, primary_key=True)
    date = db.Column(TIMESTAMP(timezone=True), nullable=False, primary_key=True)
    count_uuids = db.Column(db.Integer, server_default='0')
    count_sessions = db.Column(db.Integer, server_default='0')


class AggregateCity(db.Model):
    __tablename__ = 'stat_city'

    # pk отсутствует в БД (Нужен для миграций)
    # __table_args__ = (db.Index('ix_stat_city_tour_id_aggr_type_city_id', "aggr_type", "tour_id", "city_id"),
    #                   db.PrimaryKeyConstraint('aggr_type', 'tour_id', 'date', 'city_id'))

    tour_id = db.Column(db.Integer, db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True)
    aggr_type = db.Column(db.Enum(*list(AGGR_TYPES.keys()), name='count_type'), primary_key=True)
    date = db.Column(TIMESTAMP(timezone=True), primary_key=True)
    city_id = db.Column(db.Integer(), db.ForeignKey('cities.id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True)
    count = db.Column(db.Integer, server_default='0')


class AggregateTime(db.Model):
    __tablename__ = 'stat_time'

    tour_id = db.Column(db.Integer,
                        db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'),
                        nullable=False,
                        primary_key=True)
    min = db.Column(db.Interval, nullable=False)
    max = db.Column(db.Interval, nullable=False)
    mid = db.Column(db.Interval, nullable=False)
    count_json = db.Column(JSONB, nullable=False, default={}, server_default='{}')


class AggregateReferer(db.Model):
    __tablename__ = 'stat_referer'

    # pk отсутствует в БД (Нужен для миграций)
    __table_args__ = (db.Index('ix_stat_referer_tour_id_aggr_type_referer_host_iframe',
                               "aggr_type",
                               "tour_id",
                               "referer_host",
                               "iframe"),
                      db.PrimaryKeyConstraint('aggr_type', 'tour_id', 'date', 'referer_host', 'iframe', 'count'))

    aggr_type = db.Column(db.Enum(*list(AGGR_TYPES.keys()), name='count_type'), nullable=False)
    date = db.Column(TIMESTAMP(timezone=True), nullable=False)
    tour_id = db.Column(db.Integer,
                        db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'),
                        nullable=False)
    referer_host = db.Column(db.String(1024), nullable=True, default='', server_default='')
    iframe = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    count = db.Column(db.Integer, server_default='0')


class IkeaStat(db.Model):
    __tablename__ = 'ikea_clicks'

    id = db.Column(db.Integer(), primary_key=True)
    clicked = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    tour_id = db.Column(db.Integer,
                        db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'),
                        nullable=False)
    url = db.Column(db.Text(), nullable=False, default='', server_default='')
    ip = db.Column(INET(), nullable=False)
    user_agent = db.Column(db.Text())

    def set_info(self, request):
        """Заполняет свои поля из данных запроса request."""
        self.ip = request.remote_addr
        self.user_agent = str(request.headers.get('User-Agent'))


class StatAction(db.Model):
    __tablename__ = 'stat_actions'

    id = db.Column(db.Integer(), primary_key=True)
    tour_id = db.Column(db.Integer,
                        db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'),
                        nullable=False, index=True)
    session_key = db.Column(UUID(as_uuid=True), nullable=False)
    created = db.Column(TIMESTAMP(timezone=True), server_default=db.text('now()'), nullable=False)

    action_trigger = db.Column(db.String(16))
    action_id = db.Column(db.String(255))
