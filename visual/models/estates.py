import os
import tempfile
import uuid
import logging

from flask import abort, url_for, current_app
from flask_babel import gettext
from flask_login import current_user
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm.attributes import flag_modified
from lagring import Asset
import filetype
import ffmpeg
from PIL import Image
import boto3
import botocore

from visual.core import db, storage
from visual.util import downsize_img


class Estate(db.Model):
    __tablename__ = 'estates'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    remote_id = db.Column(db.String(255))
    synced = db.Column(db.DateTime(timezone=True))
    cnt_assets = db.Column(JSONB, nullable=False, default={}, server_default='{}')   # В виде {type: cnt, ...}

    user = db.relationship('User', foreign_keys=[user_id], backref='estates')
    tags = db.relationship('EstateTag', cascade='save-update, merge, delete, delete-orphan')
    assets = db.relationship('EstateAsset', back_populates='estate', cascade='save-update, merge, delete, delete-orphan')

    def api_repr(self, _who=None, **kwargs):
        """
        API-представление
        _who: кто смотрит. "owner" — владелец эстейта
        """
        r = {
            'id': self.id,
            'created': self.created.isoformat(),
            'user_id': self.user_id,
            'user': self.user.api_repr(),
            'title': self.title,
            'cnt_assets': self.cnt_assets,
        }
        if _who == 'owner' and current_user.is_authenticated and self.user_id == current_user.id:
            r['remote_id'] = self.remote_id
            r['synced'] = self.synced
        return {**r, **kwargs}

    def create_asset_from_brorderasset(self, br_asset, **kwargs) -> 'EstateAsset':
        """Создаёт EstateAsset из BROrderAsset. Копирует S3-объекты с новыми ключами, если нужно."""
        asset = EstateAsset(**kwargs)
        asset.type = br_asset.type
        asset.title = br_asset.title
        asset.size = br_asset.size
        asset.width = br_asset.width
        asset.height = br_asset.height
        asset.duration = br_asset.duration
        asset.tour_id = br_asset.tour_id
        asset.tour_video_id = br_asset.tour_video_id
        asset.from_br_asset_id = br_asset.id

        # Если ассет имел файл в S3, то копируем его
        if br_asset.s3key or br_asset.preview_s3key:
            s3 = boto3.resource('s3', endpoint_url=current_app.config['S3_ENDPOINT_URL'])
            s3bucket = s3.Bucket(current_app.config['S3_BUCKET'])
            uuid_key = uuid.uuid4().hex

            if br_asset.s3key:
                _, ext = os.path.splitext(br_asset.s3key)
                asset.s3key = f'estates/{self.id}/{uuid_key}{ext}'
                s3bucket.copy({'Bucket': current_app.config['S3_BUCKET'], 'Key': br_asset.s3key}, asset.s3key, {'ACL': 'public-read'})
            if br_asset.preview_s3key:
                _, ext = os.path.splitext(br_asset.preview_s3key)
                asset.preview_s3key = f'estates/{self.id}/{uuid_key}-preview{ext}'
                s3bucket.copy({'Bucket': current_app.config['S3_BUCKET'], 'Key': br_asset.preview_s3key}, asset.preview_s3key, {'ACL': 'public-read'})

        self.assets.append(asset)
        self.cnt_assets.setdefault(asset.type, 0)
        self.cnt_assets[asset.type] += 1
        flag_modified(self, 'cnt_assets')

        return asset


class EstateTag(db.Model):
    __tablename__ = 'estate_tags'

    id = db.Column(db.Integer(), primary_key=True)
    estate_id = db.Column(db.Integer, db.ForeignKey(Estate.id), nullable=False, index=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'), index=True)
    value = db.Column(db.Text)

    tag = db.relationship('Tag')

    def api_repr(self, _format_value=False, **kwargs):
        # Берём API-репрезентацию Tag и заменяем в ней id, tag_id и value
        if _format_value:
            value = self.tag.format(self.value)
        else:
            value = self.value
        r = self.tag.api_repr(id=self.id, value=value, tag_id=self.tag_id)
        # Удаляем ненужные свойства Tag
        r.pop('created', None)
        r.pop('user_id', None)
        r.pop('crm_key', None)
        if _format_value:
            r.pop('prefix', None)
            r.pop('suffix', None)
            r.pop('display_dict', None)
        # Удаляем null'ы из ответа для краткости
        r = {k: v for k, v in r.items() if v is not None}
        return {**r, **kwargs}


class EstateAsset(db.Model):
    """
    Ассеты сохраняются в S3 с ключами вида
    /estates/assets/{estate_id}/{UUID}.ext
    """
    __tablename__ = 'estate_assets'

    TYPES = ('tour', 'tour_video', 'photo', 'plan', 'screenshot', 'video', 'bank', 'other')

    # Какого размера делать превью при загрузке контента, если self.type есть в этом словаре
    PREVIEW_SIZES = {
        'photo': (128, 80),
        'plan': (128, 80),
        'screenshot': (128, 80),
        'bankx': (128, 80),
        'video': (488, 300),
    }

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    estate_id = db.Column(db.Integer(), db.ForeignKey('estates.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    type = db.Column(db.Enum(*TYPES, name='estate_asset_type'), nullable=False)
    s3key = db.Column(db.String(2048))
    preview_s3key = db.Column(db.String(2048))
    sort = db.Column(db.Integer)
    title = db.Column(db.Text)
    size = db.Column(db.Integer)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    duration = db.Column(db.Integer)
    tour_id = db.Column(db.Integer(), db.ForeignKey('tours.id', ondelete='SET NULL', onupdate='CASCADE'))
    tour_video_id = db.Column(db.Integer(), db.ForeignKey('tour_videos.id', ondelete='SET NULL', onupdate='CASCADE'))
    from_br_asset_id = db.Column(db.Integer(), db.ForeignKey('br_order_assets.id', ondelete='SET NULL', onupdate='CASCADE'))

    @property
    def url(self):
        return current_app.config['S3_URL'].format(s3_key=self.s3key) if self.s3key else None

    @property
    def preview_url(self):
        return current_app.config['S3_URL'].format(s3_key=self.preview_s3key) if self.preview_s3key else None

    estate = db.relationship('Estate', foreign_keys=[estate_id], back_populates='assets')
    tour = db.relationship('Tour')
    tour_video = db.relationship('TourVideo')

    def api_repr(self, **kwargs):
        r = {
            'id': self.id,
            'created': self.created,
            'estate_id': self.estate_id,
            'type': self.type,
            'title': self.title,
            'sort': self.sort,
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
        @todo: практически полный дубликат BROrderAsset.save_file(), рефакторить
        """
        log = logging.getLogger('estates')

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
        self.s3key = f'estates/{self.estate_id}/{uuid_key}.{ext}'
        log.debug(f'Save to S3: {self.s3key}')
        try:
            s3bucket.put_object(Key=self.s3key, Body=fh, ACL='public-read', ContentType=mime, ContentLength=self.size)
        except botocore.exceptions.ClientError as e:
            log.exception(f'Failed to save asset to S3: {e}')
            raise

        if self.type == 'video':
            # Сохраняем загрузку во временный файл для создания превьюхи
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

                log.debug(f'Create video preview {self.width}x{self.height}@{self.duration // 2} -> {EstateAsset.PREVIEW_SIZES[self.type]} ')
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
                    self.preview_s3key = f'estates/{self.estate_id}/{uuid_key}-preview.jpg'
                    log.debug(f'Save preview to {self.preview_s3key}')
                    try:
                        s3bucket.put_object(Key=self.preview_s3key, Body=preview_tmp, ACL='public-read', ContentType='image/jpeg',
                                            ContentLength=os.stat(preview_tmp.name).st_size)
                    except botocore.exceptions.ClientError as e:
                        log.exception(f'Failed to save asset to S3: {e}')
                        raise

        elif self.type in self.PREVIEW_SIZES:
            # Для остальных типов делаем превьюшку из растра
            with tempfile.NamedTemporaryFile(suffix='.jpg') as preview_tmp:
                log.debug(f'Create image preview {self.PREVIEW_SIZES[self.type]} to {preview_tmp.name}')
                with Image.open(fh) as img:
                    self.width, self.height = img.size

                downsize_img(fh, preview_tmp.name, self.PREVIEW_SIZES[self.type], 'crop')
                preview_tmp.seek(0)

                self.preview_s3key = f'estates/{self.estate_id}/{uuid_key}-preview.jpg'
                log.debug(f'Save to S3: {self.preview_s3key}')
                try:
                    s3bucket.put_object(Key=self.preview_s3key, Body=preview_tmp, ACL='public-read', ContentType='image/jpeg',
                                        ContentLength=os.stat(preview_tmp.name).st_size)
                except botocore.exceptions.ClientError as e:
                    log.exception(f'Failed to save asset to S3: {e}')
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
