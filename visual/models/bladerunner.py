import os
import datetime
import typing
import tempfile
import logging

from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from flask import abort, url_for, current_app
from flask_babel import gettext
import portion as P
import boto3
import botocore
import uuid
import filetype
import ffmpeg
from PIL import Image

from visual.util import downsize_img
from visual.core import db, storage


class SpaceTimePoint(object):
    """
    Точка в пространстве Минковского.
    Сравнение двух точек происходит только через сравнение временной координаты.
    """
    def __init__(self, coords: typing.List[float], time: datetime.datetime):
        self.coords = coords
        self.time = time

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.time == other.time
        return self.time == other

    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return self.time != other.time
        return self.time != other

    def __lt__(self, other):
        if isinstance(other, self.__class__):
            return self.time < other.time
        return self.time < other

    def __le__(self, other):
        if isinstance(other, self.__class__):
            return self.time <= other.time
        return self.time <= other

    def __gt__(self, other):
        if isinstance(other, self.__class__):
            return self.time > other.time
        return self.time > other

    def __ge__(self, other):
        if isinstance(other, self.__class__):
            return self.time >= other.time
        return self.time >= other

    def __repr__(self):
        return f'<SpaceTime {self.coords[0]:.04f}:{self.coords[1]:.04f} {self.time.strftime("%d.%m.%Y %H:%M %z")}'


class BROffice(db.Model):
    __tablename__ = 'br_offices'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    manager_id = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    city_id = db.Column(db.Integer(), db.ForeignKey('cities.id', ondelete='RESTRICT', onupdate='CASCADE'), nullable=False, index=True)
    coords = db.Column(ARRAY(db.Float(), zero_indexes=True), nullable=False)
    address = db.Column(db.String(1024))
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    manager_comment = db.Column(db.Text)
    work_start = db.Column(db.Time(timezone=True), nullable=False)
    work_end = db.Column(db.Time(timezone=True), nullable=False)

    manager = db.relationship('User', foreign_keys=[manager_id], backref='office')
    city = db.relationship('City', backref='br_offices')

    def api_repr(self, _who='customer', **kwargs):
        """
        API-представление для юзера _who: 'customer', 'operator', 'manager'.
        """
        r = {
            'id': self.id,
            'active': self.active,
            'title': self.title,
            'city': {
                'id': self.city.id,
                'title': self.city.name
            },
            'managers': {self.manager_id: self.manager.api_repr()},
        }
        if _who == 'operator' or _who == 'manager':
            r = {**r, **{
                'description': self.description,
                'coords': self.coords,
                'address': self.address,
                'work_start': self.work_start,
                'work_end': self.work_end,
            }}
        if _who == 'manager':
            r = {**r, **{
                'created': self.created.isoformat(),
                'manager_comment': self.manager_comment,
            }}
        return {**r, **kwargs}


class BROperator(db.Model):
    __tablename__ = 'br_operators'

    user_id = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True)
    office_id = db.Column(db.Integer(), db.ForeignKey('br_offices.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    active = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    work_start = db.Column(db.Time(timezone=True), nullable=False)
    work_end = db.Column(db.Time(timezone=True), nullable=False)
    manager_comment = db.Column(db.Text)

    user = db.relationship('User', foreign_keys=[user_id])
    office = db.relationship('BROffice')

    def api_repr(self, **kwargs):
        r = {
            'user': self.user.api_repr(),
            'office_id': self.office_id,
            'active': self.active,
            'work_start': self.work_start,
            'work_end': self.work_end
        }
        return {**r, **kwargs}

    def free_time_intervals(self, date: datetime.date):
        """Возвращает список свободных интервалов времени у оператора в указанный день.
        Элементы интервалов - экземпляры SpaceTimePoint"""
        a = SpaceTimePoint(self.office.coords, datetime.datetime.combine(date, max(self.work_start, self.office.work_start)))
        b = SpaceTimePoint(self.office.coords, datetime.datetime.combine(date, min(self.work_end, self.office.work_end)))
        free_time = P.closed(a, b)

        q = BROrder.query.filter(
            BROrder.operator_id == self.user_id,
            BROrder.status != 'canceled',
            db.func.date(BROrder.start) == date
        )

        for order in q.all():
            a = SpaceTimePoint(order.coords, order.start)
            b = SpaceTimePoint(order.coords, order.start + datetime.timedelta(minutes=order.tts))
            busy = P.closed(a, b)
            free_time -= busy

        # Обрезаем интервалы свободного времени отрезком [<office.coords, 00:00>, <X.coords, now()>]
        # где X — интервал, внутри которого находится now()
        tznow = datetime.datetime.now(self.office.work_start.tzinfo)
        pnow = P.singleton(SpaceTimePoint([0, 0], tznow))
        if free_time & pnow:
            for i in free_time:
                if i & pnow:
                    cut = P.closed(a, SpaceTimePoint(i.lower.coords, tznow))
                    free_time -= cut

        return free_time


class BROrder(db.Model):
    __tablename__ = 'br_orders'

    STATUSES = (
        'scheduled',                # Съёмка назначена
        'progress.enroute',         # Оператор едет-едет
        'progress.shooting',        # Оператор снимает
        'progress.shoot_complete',  # Оператор всё снял и курит
        'progress.processing',      # Сцена выгружается и обрабатывается
        'progress.review',          # Идёт проверка материалов
        'reschedule.customer',      # Нужно переназначить время, потому что облажался клиент
        'reschedule.we',            # Нужно переназначить время, потому что облажались мы
        'failed.customer',          # Заказ не выполнен по вине заказчика
        'failed.we',                # Заказ не выполнен по нашей вине
        'success',                  # Заказ выполнен
        'canceled',                 # Заказ отменён
        'smoking',                  # Технический статус. Оператор в перерыве между заказами
    )

    # Матрица переходов статусов: {тип_пользователя: {from: [to, ...]}}
    STATUS_TRANSFORM = {
        'customer': {
            'scheduled': ['reschedule.customer', 'canceled'],
            'reschedule.customer': ['scheduled', 'canceled'],
            'reschedule.we': ['scheduled', 'canceled']
        },
        'operator': {
            'scheduled': ['progress.enroute'],
            'progress.enroute': ['progress.shooting'],
            'progress.shooting': ['progress.shoot_complete'],
            'progress.shoot_complete': ['progress.processing'],
            'progress.processing': ['progress.review'],
        }
    }

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    status = db.Column(db.Enum(*STATUSES, name='br_order_status'), nullable=False)

    customer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'))
    office_id = db.Column(db.Integer, db.ForeignKey('br_offices.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    operator_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'))

    coords = db.Column(ARRAY(db.Float(), zero_indexes=True), nullable=False)
    address = db.Column(db.String(1024))
    contacts = db.Column(JSONB)

    estate_id = db.Column(db.Integer, db.ForeignKey('estates.id', ondelete='CASCADE', onupdate='CASCADE'))

    start = db.Column(db.DateTime(timezone=True))
    tts = db.Column(db.SmallInteger)

    customer_comment = db.Column(db.Text)
    manager_comment = db.Column(db.Text)
    operator_comment = db.Column(db.Text)

    cnt_assets = db.Column(JSONB, nullable=False, default={}, server_default='{}')   # В виде {type: cnt, ...}

    customer = db.relationship('User', foreign_keys=[customer_id])
    office = db.relationship('BROffice', foreign_keys=[office_id])
    operator = db.relationship('User', foreign_keys=[operator_id])
    estate = db.relationship('Estate', foreign_keys=[estate_id])
    assets = db.relationship('BROrderAsset', order_by='BROrderAsset.created.desc()')

    @classmethod
    def resolve_status_wildcard(cls, wc: str) -> list:
        """Возвращает список статусов, которые подходят под wildcard в `wc`. Обычные статусы
        тоже понимает."""
        if wc.endswith('.*'):
            result = [st for st in cls.STATUSES if st.startswith(wc[:-1])]
        else:
            result = [wc]
        return result

    def api_repr(self, _who='customer', **kwargs):
        """
        API-представление для юзера _who: 'customer', 'operator', 'manager'.
        """
        r = {
            'id': self.id,
            'status': self.status,
            'customer': self.customer.api_repr() if self.customer_id else None,
            'coords': self.coords,
            'address': self.address,
            'contacts': self.contacts,
            'estate': self.estate.api_repr() if self.estate_id else None,
            'start': self.start,
            'tts': self.tts,
            'customer_comment': self.customer_comment,
            'office': self.office.api_repr(_who)
        }

        if _who == 'operator' or _who == 'manager':
            r['operator'] = self.operator.api_repr() if self.operator_id else None
            r['operator_comment'] = self.operator_comment
            r['cnt_assets'] = self.cnt_assets

        if _who == 'manager':
            r['manager_comment'] = self.operator_comment

        if _who == 'success':
            if self.status == '':
                r['cnt_assets'] = self.cnt_assets

        return {**r, **kwargs}


class BROrderAsset(db.Model):
    """
    Ассеты сохраняются в S3 с ключами вида
    /bladerunner/assets/{order_id}/{UUID}.ext
    """
    __tablename__ = 'br_order_assets'

    TYPES = ('tour', 'tour_video', 'photo', 'plan', 'screenshot', 'video', 'other', 'bank')

    # Какого размера делать превью при загрузке контента, если self.type есть в этом словаре
    PREVIEW_SIZES = {
        'photo': (128, 80),
        'plan': (128, 80),
        'screenshot': (128, 80),
        'video': (488, 300),
        'bank': (128, 80),
    }

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    order_id = db.Column(db.Integer(), db.ForeignKey('br_orders.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    operator_id = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    type = db.Column(db.Enum(*TYPES, name='br_order_asset_type'), nullable=False)
    s3key = db.Column(db.String(2048))
    preview_s3key = db.Column(db.String(2048))
    size = db.Column(db.Integer)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    duration = db.Column(db.Integer)
    title = db.Column(db.Text)
    tour_id = db.Column(db.Integer(), db.ForeignKey('tours.id', ondelete='SET NULL', onupdate='CASCADE'))
    tour_video_id = db.Column(db.Integer(), db.ForeignKey('tour_videos.id', ondelete='SET NULL', onupdate='CASCADE'))
    product_meta = db.Column(JSONB)

    @property
    def url(self):
        return current_app.config['S3_URL'].format(s3_key=self.s3key) if self.s3key else None

    @property
    def preview_url(self):
        return current_app.config['S3_URL'].format(s3_key=self.preview_s3key) if self.preview_s3key else None

    operator = db.relationship('User', foreign_keys=[operator_id])
    tour = db.relationship('Tour')
    tour_video = db.relationship('TourVideo')

    def api_repr(self, **kwargs):
        r = {
            'id': self.id,
            'created': self.created,
            'order_id': self.order_id,
            'operator': self.operator.api_repr(),
            'type': self.type,
            'title': self.title,
            'product_meta': self.product_meta,
            'duration': self.duration,
            'size': self.size,
            'width': self.width,
            'height': self.height,
        }
        if self.type == 'tour' and self.tour_id:
            r['tour_id'] = self.tour_id
            r['tour'] = {
                'id': self.tour.id,
                'hidden': self.tour.hidden,
                'preview': self.tour.preview.url if self.tour.preview else None,
                'screen': self.tour.screen.url if self.tour.screen else None,
                'title': self.tour.title
            }
            r['url'] = url_for('front.tour', tour_id=self.tour_id)
            r['preview_url'] = self.tour.preview.url if self.tour else None
        elif self.type == 'tour_video' and self.tour_video_id:
            r['tour_video_id'] = self.tour_video_id
            r['tour_video'] = {
                'id': self.tour_video.id,
                'title': self.tour_video.title,
                'fps': self.tour_video.fps,
            }
            r['url'] = self.tour_video.url
            r['preview_url'] = self.tour_video.preview
            r['size'] = self.tour_video.size
            r['width'] = self.tour_video.width
            r['height'] = self.tour_video.height
            r['duration'] = self.tour_video.duration
        else:
            r['url'] = self.url
            r['preview_url'] = self.preview_url

        return {**r, **kwargs}

    @property
    def is_heavy(self):
        """True, если этот ассет считается тяжёлым, и копировать или скачивать его лучше асинхронно."""
        return self.type not in ('tour', 'tour_video')

    def save_file(self, fh):
        """Помещает файл fh в хранилище и пишет в себя его S3-ключ.
        Для картинок и видео создаёт (в зависимости от self.type) превью.
        Когда может, присваивает значения self.size, self.duration, self.width, self.height
        """
        log = logging.getLogger('bladerunner')

        s3 = boto3.resource('s3', endpoint_url=current_app.config['S3_ENDPOINT_URL'])
        s3bucket = s3.Bucket(current_app.config['S3_BUCKET'])
        uuid_key = uuid.uuid4().hex

        # Считаем размер файла
        fh.seek(0, os.SEEK_END)
        self.size = fh.tell()
        fh.seek(0)
        log.debug(f'Size: {self.size}')

        # Считаем тип файла: для расширения и mime-type объекта в S3
        buf = fh.read(filetype.utils._NUM_SIGNATURE_BYTES)
        fh.seek(0)
        kind = filetype.guess(buf)
        if kind is not None:
            ext = kind.extension
            mime = kind.mime
        else:
            ext = 'file'
            mime = 'application/octet-stream'
        log.debug(f'KIND {kind}, ext={ext}, mime={mime}')

        # Сохраняем исходный файл
        self.s3key = f'bladerunner/orders/{self.order_id}/{uuid_key}.{ext}'
        log.debug(f'Save to S3: {self.s3key}')
        try:
            s3bucket.put_object(Key=self.s3key, Body=fh, ACL='public-read', ContentType=mime, ContentLength=self.size)
        except Exception as e:
            log.exception(f'Failed to save asset')
            raise

        if self.type == 'video':
            # Сохраняем загрузку во временный файл, чтобы узнать его тип
            with tempfile.NamedTemporaryFile() as tmp:
                log.debug(f'SAVE TO {tmp.name}')
                fh.seek(0)
                tmp.write(fh.read())
                fh.seek(0)

                # Для видео создаём превьюшку
                probe = ffmpeg.probe(tmp.name, select_streams='v')
                stream = probe['streams'][0]
                self.width = stream['width']
                self.height = stream['height']
                self.duration = round(float(stream['duration']))

                log.debug(f'Create video preview {self.width}x{self.height}@{self.duration // 2} -> {BROrderAsset.PREVIEW_SIZES[self.type]} ')
                with tempfile.NamedTemporaryFile(suffix='.jpg') as preview_tmp:
                    try:
                        ffmpeg \
                            .input(tmp.name, ss=self.duration // 2) \
                            .filter('scale', self.width // 2, -1) \
                            .output(preview_tmp.name, vframes=1) \
                            .overwrite_output() \
                            .run(capture_stdout=True, capture_stderr=True)
                    except ffmpeg.Error as e:
                        log.error(f'Не получилось создать превьюшку: {e}, {e.stderr.decode()}')
                        raise

                    preview_tmp.seek(0)
                    self.preview_s3key = f'bladerunner/orders/{self.order_id}/{uuid_key}-preview.jpg'
                    log.debug(f'Save preview to {self.preview_s3key}')
                    try:
                        s3bucket.put_object(Key=self.preview_s3key, Body=preview_tmp, ACL='public-read', ContentType='image/jpeg',
                                            ContentLength=os.stat(preview_tmp.name).st_size)
                    except Exception as e:
                        log.exception(f'Failed to save asset')
                        raise

        elif self.type in self.PREVIEW_SIZES:
            # Для остальных типов делаем превьюшку из растра
            with tempfile.NamedTemporaryFile(suffix='.jpg') as preview_tmp:
                log.debug(f'Create image preview {self.PREVIEW_SIZES[self.type]} to {preview_tmp.name}')
                with Image.open(fh) as img:
                    self.width, self.height = img.size

                downsize_img(fh, preview_tmp.name, self.PREVIEW_SIZES[self.type], 'crop')
                preview_tmp.seek(0)

                self.preview_s3key = f'bladerunner/orders/{self.order_id}/{uuid_key}-preview.jpg'
                log.debug(f'Save to S3: {self.preview_s3key}')
                try:
                    s3bucket.put_object(Key=self.preview_s3key, Body=preview_tmp, ACL='public-read', ContentType='image/jpeg',
                                        ContentLength=os.stat(preview_tmp.name).st_size)
                except Exception as e:
                    log.exception(f'Failed to save asset')
                    raise

    def delete_files(self):
        """Удаляет из S3 файлы ассета."""
        objs = []
        if self.s3key:
            objs.append({'Key': self.s3key})
        if self.preview_s3key:
            objs.append({'Key': self.preview_s3key})
        if objs:
            try:
                s3 = boto3.resource('s3', endpoint_url=current_app.config['S3_ENDPOINT_URL'])
                s3bucket = s3.Bucket(current_app.config['S3_BUCKET'])
                s3bucket.delete_objects(
                    Delete={
                        'Objects': objs,
                        'Quiet': False
                    }
                )
            except botocore.exceptions.ClientError as e:
                current_app.logger.exception(f'Failed to delete S3 objects in {self.__class__.name}.delete_files(): {e}')
