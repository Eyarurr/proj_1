import copy
import os
from collections import OrderedDict
import shutil
import tempfile
import subprocess
import json
import gzip
from datetime import datetime, timedelta
from pytz import timezone
import hashlib

from flask import request, current_app, url_for, g, abort
from flask_login import current_user
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.hybrid import hybrid_property
from flask_babel import to_user_timezone, gettext
from lagring.assets.image import ImageAsset
from lagring.assets.directory import DirectoryAsset
from PIL import Image
import requests

from visual.core import db, storage
from visual.util import get_lang, dict_merge
from visual.models.statistics import AggregateCount

VALIDATION_EXCEPTIONS = (ValueError, KeyError, TypeError, AssertionError)


class Footage(db.Model, storage.Entity):
    """
    Съёмка.
    """
    __tablename__ = 'footages'

    TYPES = OrderedDict([
        ('real', '3D-фотосъёмка'),
        ('virtual', 'Виртуальный'),
        ('outside', 'Outside'),
    ])

    STATUSES = OrderedDict([
        ('loading', 'Загрузка'),
        ('queued', 'В очереди'),
        ('processing', 'Сборка'),
        ('testing', 'Тестирование'),
        ('published', 'Опубликован'),
        ('banned', 'Забанен')
    ])

    INIT_META_LOADING = {
        'models': [],
        'skyboxes': {},
        'options': {
            'render_type': 'vray',
            'model_lowpoly': True,
            'coords_from_obj': True,
            'dollhouse': True
        },
        'floor_heights': {}
    }

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'))
    updated = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT', onupdate='CASCADE'), nullable=False,
                        index=True)
    type = db.Column(db.Enum(*list(TYPES.keys()), name='footage_type'))
    _status = db.Column(db.Enum(*list(STATUSES.keys()), name='footage_status'), server_default='loading',
                        nullable=False)
    meta = db.Column(JSONB, nullable=False, default={}, server_default='{}')

    files = DirectoryAsset()

    creator = db.relationship('User', foreign_keys=[created_by])
    user = db.relationship('User', foreign_keys=[user_id])

    def api_view(self, **kwargs):
        t = {
            'id': self.id,
            'created': self.created,
            'updated': self.updated,
            'user_id': self.user_id,
            'type': self.type,
            'status': self.status
        }

        t = {**t, **kwargs}

        return {k: v for k, v in t.items() if v is not None}

    def age(self):
        """Возвращает количество дней, которое съёмка не изменялась (по Footage.updated)"""
        return (datetime.now(tz=self.updated.tzinfo) - self.updated).days

    def delete(self):
        """Убивает себя с ассетами и все туры, созданные на основе себя через Tour.delete()
        """
        for tour in self.tours:
            tour.delete(check_orphan_footage=False)

        db.session.delete(self)

        del self.files

    def mkdir(self, clean=False):
        """Создаёт пустую директорию в ассете files, если такого ассета нет. При clean=True создаёт пустую директорию всегда."""
        if self.files and not clean:
            return

        emptydir = tempfile.mkdtemp()
        os.chmod(emptydir, 0o755)
        self.files = emptydir
        os.rmdir(emptydir)

    def in_files(self, *args):
        """Возвращает полный путь к файлу, чей путь строится из аргументов (os.path.join)"""
        return os.path.join(self.files.abs_path, *args)

    @property
    def min_res(self):
        """Возвращает минимальное разрешение панорам съёмки."""
        if self.meta and 'resolutions' in self.meta:
            return min(self.meta['resolutions'])
        else:
            return None

    @property
    def max_res(self):
        """Возвращает максимальное разрешение панорам съёмки."""
        if self.meta and 'resolutions' in self.meta:
            return max(self.meta['resolutions'])
        else:
            return None

    def choose_res(self, client_resolution):
        """Подбирает разрешение, лучше всего подходящее для вьюпорта с максимальной шириной client_resolution."""
        if not self.meta.get('resolutions'):
            return None

        # Разница между клиентским разрешением и разрешениями съёмки
        estimates = {res: client_resolution - res for res in self.meta['resolutions']}

        # Там, где панорамы придётся увеличивать, ухудшаем оценку вдвое
        estimates = {k: v * current_app.config.get('UPSCALE_UNDESIRABILITY', 20) if v > 0 else abs(v) for k, v in
                     estimates.items()}

        return min(estimates.items(), key=lambda x: x[1])[0]

    def count_panoramas(self):
        """Возвращает количество скайбоксов для традиционных или фреймов для outside-туров."""
        try:
            if self.type == 'outside':
                n = 0
                for s in list(self.meta.get('sets', {}).values()):
                    n += len(s.get('frames', {}))
                return n
            else:
                if self._status in ('loading', 'processing'):
                    return len(self.meta.get('_loading', {}).get('skyboxes', []))
                else:
                    return len(self.meta.get('skyboxes', {}))
        except (ValueError, AttributeError):
            return 0

    @property
    def allowed_statuses(self):
        """Возвращает список статусов, в который можно перейти из текущего.
        """
        map = {
            'loading': ['processing', 'queued', 'testing'],
            'queued': ['loading', 'processing'],
            'processing': ['loading', 'queued', 'testing'],
            'testing': ['published', 'loading'],
            'published': ['banned', 'testing', 'loading'],
            'banned': ['published']
        }
        return map.get(self.status, [])

    @hybrid_property
    def status(self):
        return self._status

    @status.setter
    def status(self, new_status):
        if self.status == new_status:
            return

        if new_status not in self.allowed_statuses:
            return

        if self.type != 'real':
            if self.status == 'queued':
                self.meta.pop('_queued', None)
                flag_modified(self, 'meta')

            if self.status == 'processing':
                self.meta.pop('_processing', None)
                flag_modified(self, 'meta')

            # * -> loading, пересборка
            if new_status == 'loading':
                # Удаляем директории с панорамамаи, моделями и планировками
                for folder in self.meta.get('resolutions', []) + ['models', 'maps']:
                    shutil.rmtree(self.in_files(str(folder)), ignore_errors=True)

                # Стираются обычные свойства
                meta_keys = ['model', 'mtl', 'floors', 'skyboxes', 'start', 'passways', 'binocular',
                             'model_size', 'model_size_gz', 'resolutions', 'model_format']
                for meta_key in meta_keys:
                    if meta_key in self.meta:
                        del self.meta[meta_key]
                        flag_modified(self, 'meta')

                if self.status == 'published':
                    self.meta['_loading'] = self.INIT_META_LOADING
                    flag_modified(self, 'meta')

            # testing -> published
            # Удаляем исходники в basedir/_loading и мету о них в meta['_loading']
            if new_status == 'published':
                shutil.rmtree(self.in_files('_loading'), ignore_errors=True)
                if '_loading' in self.meta:
                    self.meta.pop('_loading', None)
                    flag_modified(self, 'meta')

        self._status = new_status

    def total_size(self):
        """Возвращает суммарный размер всех панорам и модели тура из записанных в свойствах model_size и Skybox.files_size
        """
        if self.status not in ('testing', 'published'):
            return 0

        size = self.meta.get('model_size', 0)
        for skybox in self.meta.get('skyboxes', {}).values():
            if 'files_size' not in skybox:
                continue
            for res, sizes in skybox['files_size'].items():
                if res.isnumeric():
                    size += sum(sizes.values())
        return size

    def calc_passways(self):
        """Вычисляет граф достижимости между опорными точками съёмки по модели и возвращает его.
        В случае ошибки выбрасывает ValueError: если нет скайбоксов в мете или сдохла внешняя утилита
        Внимание, потенциально тяжёлые вычисления!
        """
        if 'skyboxes' not in self.meta:
            raise ValueError('Нет skyboxes в мете')

        cmd = current_app.config['CALC_PASSWAYS_CMD'] + [self.in_files(self.meta['model'])]
        coords = {sid: {'pos': box['pos']} for sid, box in self.meta['skyboxes'].items() if not box.get('disabled')}
        # @todo: когда python<3.7 умрёт, заменить universal_newlines, stdout и stderr на capture_output=True
        run = subprocess.run(cmd, input=json.dumps(coords), universal_newlines=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        if run.returncode != 0:
            raise ValueError('calc_passways завершился с кодом {}: {}'.format(run.returncode, run.stderr))
        output = json.loads(run.stdout)

        # Приводим выдачу calc_passways к форме [(a, b), (b, c), ...]
        passways = []
        for src, dests in output.items():
            for dst in dests:
                if (dst, src) not in passways:
                    passways.append((src, dst))

        return passways

    def wurst_schneider(self, source, box_id, render_type='vray', eye=None, double=False, jpeg_quality=85):
        """
        Нарезает грани скайбокса из отрендерённой колбасы. Кладёт файлы в нужные директории, добавляет скайбокс в мету.
        :param source: путь к колбасе
        :param box_id: id скайбокса
        :param render_type: тип рендера: 'vray'|'corona'
        :param eye: для какого глаза: 'left', 'right' или None для центрального
        :param double: двойная панорама для обоих глаз. eye при этом должен быть всё равно установлен
        :param jpeg_quality: качество сжатия JPEG
        """
        if jpeg_quality is None:
            jpeg_quality = 85
        skybox_width = 12 if double and eye else 6
        skybox_type = 'center' if not eye else eye
        size = {str(res): {skybox_type: 0} for res in self.meta['resolutions']}
        max_res = self.max_res
        with Image.open(source) as wurst:
            if wurst.width < max_res * skybox_width or wurst.height < max_res or wurst.width != wurst.height * skybox_width:
                message = gettext('Panorama should be at least %(std)s px, you\'ve got %(wrong)s.', std='{:d}x{:d}'.format(
                    max_res * skybox_width, max_res), wrong='{:d}x{:d}'.format(wurst.width, wurst.height))
                raise ValueError(message)

            # Номер куска в колбасе, transpose, поворот
            rules = {'vray': [
                (2, Image.FLIP_LEFT_RIGHT, None),
                (0, Image.FLIP_LEFT_RIGHT, None),
                (4, Image.FLIP_TOP_BOTTOM, -90),
                (5, Image.FLIP_TOP_BOTTOM, 90),
                (3, Image.FLIP_LEFT_RIGHT, None),
                (1, Image.FLIP_LEFT_RIGHT, None)
            ],
                'corona': [
                    (1, Image.FLIP_LEFT_RIGHT, None),
                    (3, Image.FLIP_LEFT_RIGHT, None),
                    (4, Image.FLIP_TOP_BOTTOM, None),
                    (5, Image.FLIP_TOP_BOTTOM, None),
                    (2, Image.FLIP_LEFT_RIGHT, None),
                    (0, Image.FLIP_LEFT_RIGHT, None)
                ]}

            wurst = wurst.convert("RGB")

            for i, (face_num, transpose, rotate) in enumerate(rules[render_type]):
                shift_width = wurst.width / 2 if double and eye == 'right' else 0
                face = wurst.crop(
                    [shift_width + i * wurst.height, 0, shift_width + (i + 1) * wurst.height, wurst.height])
                if rotate is not None:
                    face = face.rotate(rotate)
                if transpose is not None:
                    face = face.transpose(transpose)

                for res in sorted(self.meta['resolutions'], reverse=True):
                    if res != wurst.height:
                        face.thumbnail([res, res], Image.LANCZOS)
                    if eye:
                        skybox_dir = os.path.join('{:d}'.format(res), eye)
                        os.makedirs(self.in_files(skybox_dir), mode=0o755, exist_ok=True)
                    else:
                        skybox_dir = '{:d}'.format(res)
                    face_name = self.in_files('{}/{}-{:d}.jpg'.format(skybox_dir, box_id, face_num))
                    face.save(face_name, "JPEG", quality=jpeg_quality, optimize=True)
                    size[str(res)][skybox_type] += os.stat(face_name).st_size
            dict_merge(self.meta['skyboxes'][str(box_id)].setdefault('files_size', {}), size)

    def get_gz_size(self, compress_level=None):
        """Возвращает кортеж из размера гзипованного файла и размера негзипованного.
        """
        if compress_level is None:
            compress_level = current_app.config.get('NGINX_GZIP_LEVEL', 6)
        if 'model' not in self.meta:
            return 0, 0
        model_path = self.in_files(self.meta['model'])
        size = os.stat(model_path).st_size

        with open(model_path, 'rb') as fh:
            compressed = gzip.compress(fh.read(), compress_level)

        return len(compressed), size

    def save_meta(self, meta):
        for key, value in meta.items():
            if key in ('model', 'mtl', 'model_format', 'model_size', 'model_size_gz', 'sources',
                       'resolutions', 'passways', 'binocular', 'languages', 'default_lang'):
                self.meta[key] = value
            elif key == 'skyboxes':
                self.meta['skyboxes'] = {}
                for tour in self.tours:
                    tour.meta['skyboxes'] = {}
                    for skybox_id, skybox in value.items():
                        tour.meta['skyboxes'][skybox_id] = {'title': skybox.get('title', '')}

                for skybox_id, skybox in value.items():
                    if 'title' in skybox:
                        del skybox['title']
                    self.meta['skyboxes'][skybox_id] = skybox
            elif key == 'floors':
                self.meta['floors'] = {}
                for tour in self.tours:
                    tour.meta['floors'] = {}
                    for floor_id, floor in value.items():
                        tour.meta['floors'][floor_id] = {'title': floor.get('title', '')}

                for floor_id, floor in value.items():
                    if 'title' in floor:
                        del floor['title']
                    self.meta['floors'][floor_id] = floor
            else:
                for tour in self.tours:
                    tour.meta[key] = value

            flag_modified(self, 'meta')
            for tour in self.tours:
                flag_modified(tour, 'meta')

    def load_meta_from_file(self, source_key=None):
        json_dir = self.in_files('_meta.json')
        if os.path.exists(json_dir):
            with open(json_dir, 'r') as meta:
                meta = json.loads(meta.read())
                self.save_meta(meta)

            if source_key is not None:
                self.meta['sources'] = source_key

            os.remove(self.in_files(json_dir))
        db.session.commit()


class Tour(db.Model, storage.Entity):
    """
    3D-тур.
    """
    __tablename__ = 'tours'

    GALLERY_OPTIONS = OrderedDict([
        (None, 'Не модерировано'),
        (0, 'Не показывать'),
        (1, 'Показывать в галерее'),
        (100, 'Показывать на главной'),
    ])

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'))
    updated = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    footage_id = db.Column(db.Integer, db.ForeignKey('footages.id', ondelete='RESTRICT', onupdate='CASCADE'),
                           nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT', onupdate='CASCADE'), nullable=False,
                        index=True)
    folder_id = db.Column(db.Integer, db.ForeignKey('folders.id', ondelete='SET NULL', onupdate='CASCADE'),
                          nullable=True, index=True)
    hidden = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    title = db.Column(db.String(255))
    password_hash = db.Column(db.String(32))
    password_in_url = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    traffic_today = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    traffic_total = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    # Разрешает ли пользователь показывать тур в галерее?
    gallery_user = db.Column(db.Boolean, nullable=True, default=True, server_default='t')

    # Решение админа о показе в галерее self.GALERY_OPTIONS):
    gallery_admin = db.Column(db.Integer, nullable=True, index=True)

    # Порядок сортировки в галерее по умолчанию
    gallery_sort = db.Column(db.Integer, nullable=True, index=True)

    meta = db.Column(JSONB, nullable=False, default={}, server_default='{}')

    preview = ImageAsset(width=330, height=219, transform='crop')
    screen = ImageAsset(width=1116, height=744, transform='crop',)
    files = DirectoryAsset()

    footage = db.relationship('Footage', backref='tours')
    user = db.relationship('User', foreign_keys=[user_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    gallery_tags = db.relationship('TourGalleryTag', order_by='TourGalleryTag.tag',
                                   cascade="save-update, merge, delete, delete-orphan")
    features = db.relationship('TourFeature', cascade="save-update, merge, delete, delete-orphan")
    paid_features_rel = db.relationship('TourPaidFeature', cascade="save-update, merge, delete, delete-orphan")
    folder = db.relationship('Folder', backref='tours')

    @staticmethod
    def hash_password(data):
        return hashlib.md5((data + current_app.config['TOUR_SALT']).encode()).hexdigest()

    def check_password(self, password=None, password_hash=None):
        """Проверяет, подходит ли пароль `password` или его хеш `password_hash` для этого тура, если он запаролен.
        К незапароленнному туру подойдёт любой пароль"""
        if self.password_hash is None:
            return True
        if password_hash is not None and self.password_hash == password_hash:
            return True
        if password is not None and Tour.hash_password(password) == self.password_hash:
            return True
        return False

    @staticmethod
    def statistics_subquerys():
        """Возвращает два подзапроса для статистики. DEPRECATED"""
        all_stat = db.session \
            .query(AggregateCount.tour_id, db.func.sum(AggregateCount.count_sessions).label('count_sessions')) \
            .filter(AggregateCount.aggr_type == 'year') \
            .group_by(AggregateCount.tour_id) \
            .subquery()

        day_stat = db.session \
            .query(AggregateCount.tour_id, db.func.sum(AggregateCount.count_sessions).label('count_sessions')) \
            .filter(AggregateCount.aggr_type == 'hour',
                    db.func.date_trunc('day', AggregateCount.date) == db.func.current_date()) \
            .group_by(AggregateCount.tour_id, db.func.date_trunc('day', AggregateCount.date)) \
            .subquery()

        return all_stat, day_stat

    def meta_full(self, use_host=False, pseudo_properties=True):
        """Возвращает self.footage.meta + self.meta, дополненную псевдосвойствами (берутся из модели, отсутствуют в
        самой мете).

        use_host: Отдавать абсолютные урлы для псевдосвойств.
        pseudo_properties: включать псевдосвойства, которые берутся из модели (id, created, updated, folder_id, type,
          title, status, hidden, gallery_user, gallery_admin, baseurl, tour_baseurl, preview, screen)
        """

        def _url(url):
            if use_host:
                return 'http://' + request.host + url
            else:
                return url

        meta = copy.deepcopy(self.footage.meta)

        dict_merge(meta, self.meta)

        # В результате мержа могут получиться ошибочные данные. Например, если в TourMeta был определён скайбокс
        # только с полем title, а в FootageMeta такого скайбокса не было, то мы получим скайбокс без координаты,
        # и плеера могут на нём попадать. @todo: подумать, какие тут ещё могут быть проверки
        if 'skyboxes' in meta:
            skyboxes = {}
            for box_id, box in meta['skyboxes'].items():
                if 'pos' in box and 'q' in box:
                    skyboxes[box_id] = box
            meta['skyboxes'] = skyboxes

        if pseudo_properties:
            meta['id'] = self.id
            if self.created:
                # current_user можеть быть None вне request context!
                # @todo: и возможно, to_user_timezone нужно делать на фронте уже, а не тут
                meta['created'] = to_user_timezone(
                    self.created).isoformat() if current_user and current_user.is_authenticated else self.created.isoformat()
            if self.updated:
                meta['updated'] = to_user_timezone(
                    self.updated).isoformat() if current_user and current_user.is_authenticated else self.updated.isoformat()
            meta['footage_id'] = self.footage_id
            meta['user_id'] = self.user_id
            meta['folder_id'] = self.folder_id
            meta['type'] = self.footage.type
            meta['title'] = self.title
            meta['status'] = self.footage.status
            meta['hidden'] = self.hidden
            if self.gallery_user != None:
                meta['gallery_user'] = self.gallery_user
            if self.gallery_admin != None:
                meta['gallery_admin'] = self.gallery_admin

            if self.footage.files:
                meta['baseurl'] = _url(self.footage.files.url) + '/'
            if self.files:
                meta['tour_baseurl'] = _url(self.files.url) + '/'
            if self.screen:
                meta['screen'] = _url(self.screen.url)
            if self.preview:
                meta['preview'] = _url(self.preview.url)

            meta['paid_features_time_left'] = self.paid_features_time_left()

        return meta

    def features_strings(self):
        """Возвращает список фич списком строк (а не списком TourFeature, как Tour.features)."""
        return [_.feature for _ in self.features]

    def save_features(self):
        """Пересчитывает и сохраняет в TourFeatures список фич тура. Возможные значения элементов списка:
        dollhouse, binocular, walk, audio, overlays, navigator, toolbar, branding, blotch, no_minimap, external_meta.
        Возвращает set с фичами.
        """
        features = set()
        symptoms = {
            'mtl': 'dollhouse',
            'binocular': 'binocular',
            'walk': 'walk',
            'audio': 'audio',
            'overlays': 'overlays',
            'external_meta': 'external_meta',
            'active_meshes': 'active_meshes',
            'navigator': 'navigator',
            'toolbar': 'toolbar',
            'branding': 'branding',
            'blotch': 'blotch',
            'shadows': 'shadows',
        }
        meta = self.meta_full(pseudo_properties=False)
        for meta_key, feature in symptoms.items():
            if meta.get(meta_key):
                features.add(feature)

        # фича 'clickable' означает наличие overlays[x]['actions']['click'] или active_meshes[x]['actions']['click']
        if meta.get('active_meshes'):
            for mesh in meta['active_meshes'].values():
                if mesh.get('actions', {}).get('click'):
                    features.add('clickable')

        # фича 'no_minimap' добавляется в случае, когда хотя бы у одного этажа
        # нет большой и малой планировки (Floor.big и Floor.small)
        _ = ['big' in val and 'small' in val for val in meta.get('floors', {}).values()]

        if not all(_):
            features.add('no_minimap')

        if 'clickable' not in features and meta.get('overlays'):
            for overlay in meta['overlays'].values():
                if overlay.get('actions', {}).get('click'):
                    features.add('clickable')

        if self.password_hash:
            features.add('with_password')
        # Сохраняем в базу
        o = []
        TourFeature.query.filter_by(tour_id=self.id).delete(synchronize_session=False)
        for feature in features:
            o.append({'tour_id': self.id, 'feature': feature})
        db.session.bulk_insert_mappings(TourFeature, o)

        return features

    def paid_features_time_left(self):
        """Возвращает платные фичи в виде словаря {feature: days_left, ...}, где days_left - количество полных дней до окончания
        действия фичи. 0 означает, что фича ещё активна, но заэкспайрится в течение суток"""
        return {f.feature: (f.paid_till - datetime.now(tz=f.paid_till.tzinfo)).days for f in self.paid_features_rel}

    def api_view(self, **kwargs):
        t = {
            'id': self.id,
            'created': self.created,
            'updated': self.updated,
            'user_id': self.user_id,
            'folder_id': self.folder_id,
            'footage_id': self.footage_id,
            'hidden': self.hidden,
            'title': self.title,
            'gallery_user': self.gallery_user,
            'gallery_admin': self.gallery_admin
        }
        if self.preview:
            t['preview'] = self.preview.url
        if self.screen:
            t['screen'] = self.screen.url

        t = {**t, **kwargs}

        return {k: v for k, v in t.items() if v is not None}

    def badge(self):
        """
        Возвращает структуру TourBadge для API (https://docs.google.com/document/d/11ZjR33CQE-JeHiQrI6jQx4O3D6woXDkNNYxYVLEDk1U/edit#heading=h.w3btvxit8rc7)
        :return: TourBadge
        """
        t = {
            'id': self.id,
            'created': self.created.isoformat(),
            'updated': self.updated.isoformat(),
            'type': self.footage.type,
            'title': self.title,
            'resolutions': self.footage.meta.get('resolutions'),
            'features': self.features_strings()
        }
        if self.preview:
            t['preview'] = self.preview.url
        if self.screen:
            t['screen'] = self.screen.url
        t['hidden'] = self.hidden
        return t

    def __repr__(self):
        return '<Tour %d:%s>' % (self.id or 0, self.title)

    def delete(self, check_orphan_footage=True):
        """Правильно убивает себя с ассетами и удаляя себя из презентаций, где используется.
        При check_orphan_footage удаляет съёмку, если у неё больше не осталось туров."""

        # Смотрим, в каких презентациях используется тур
        from visual.models.multimedia import OfferTour
        used = [str(x[0]) for x in db.session.query(OfferTour.offer_id).filter(OfferTour.tour_id == self.id).all()]
        if used:
            db.session.execute('UPDATE offers SET cnt_tours = cnt_tours - 1 WHERE id in(%s)' % ','.join(used))

        # Если у нашей съёмки мы были последний туром, то убиваем и съёмку тоже
        db.session.delete(self)

        if check_orphan_footage:
            if len(self.footage.tours) == 0:
                self.footage.delete()

        # Потенциально долгие операции, которые хорошо бы выполнять, если удаление прошло успешно (после успешного коммита)
        del self.preview
        del self.screen
        del self.files

    def mkdir(self, clean=False):
        """Создаёт пустую директорию в ассете files, если такого ассета нет. При clean=True создаёт пустую директорию всегда."""
        if self.files and not clean:
            return

        emptydir = tempfile.mkdtemp()
        os.chmod(emptydir, 0o755)
        self.files = emptydir
        os.rmdir(emptydir)

    def check(self, files=False):
        """Проверяет тур на наличие ошибок"""
        checkers = {
            'real': TourCheckerInside,
            'virtual': TourCheckerInside,
            'outside': TourCheckerOutside,
        }
        if self.footage.type not in checkers:
            return []
        return checkers[self.footage.type](self, files).check()

    def in_files(self, *args):
        """Возвращает полный путь к файлу, чей путь строится из аргументов (os.path.join)"""
        return os.path.join(self.files.abs_path, *args)

    @property
    def editable(self, user=None):
        """Можно ли редактировать тур юзеру user? Если user is None, то current_user."""
        if user is None:
            user = current_user

        if not user.is_authenticated:
            return False

        if user.has_role('tours'):
            return True
        else:
            if self.footage.status in ('testing', 'published') and self.user_id == user.id and not user.deleted:
                return True

        return False

    @property
    def showable(self, user=None):
        """Можно ли посмотреть этот тур юзеру user? Если user is None, то current_user."""
        if user is None:
            user = current_user

        is_owner = user.is_authenticated and user.id == self.user_id
        is_manager = user.is_authenticated and user.team_member is not None

        ok = False
        # Статус съёмки
        if self.footage.status in ('testing', 'published'):
            ok = True
        elif self.footage.status in ('banned',):
            ok = is_owner

        # Tour.hidden
        if self.hidden:
            ok = ok and (is_owner or is_manager)

        return ok

    def shareable(self):
        """
        Можно ли расшарить этот тур юзеру, с учетом grace периода и бесплатного периода хостинга туров.
        Иными словами, можно ли этот тур смотреть кому-нибудь, кроме владельца.
        :return: bool
        """
        # Виртостер не подключен
        if 'virtoaster' not in self.user.products:
            return False

        tz = current_user.timezone if current_user.is_authenticated and current_user.timezone else 'Etc/UTC'
        lpt = self.user.products['virtoaster'].last_payment_time
        now = datetime.now(tz=timezone(tz))
        tfhp = current_app.config.get('TOURS_FREE_HOSTING_PERIOD')
        grace_period = current_app.config.get('GRACE_PERIOD')
        release_date = datetime.strptime(current_app.config.get('VIRTOASTER_NEW_RULES_RELEASE_DATE'), '%Y-%m-%d').replace(tzinfo=timezone(tz))

        # Платные юзеры Виртостера
        if self.user.products['virtoaster'].plan_id != 0:
            return True

        # Бесплатные юзеры
        if self.user.products['virtoaster'].plan_id == 0:
            # дата создания юзера или дата последнего его платежа, что позднее
            actual_date = max(self.user.created, lpt) if lpt else self.user.created

            # юзер создан после релиза
            if release_date < self.user.created:
                return True if (actual_date + timedelta(days=grace_period)) > now else False
            # юзер создан до релиза
            else:
                # не было подписок
                if not lpt:
                    return True if (actual_date + timedelta(days=grace_period)) > now else False
                # были подписки
                else:
                    # отменившие подписку до релиза
                    if release_date - timedelta(days=tfhp) < lpt + timedelta(days=grace_period) < release_date:
                        return True if lpt + timedelta(days=(grace_period+tfhp)) > now else False
                    # отменившие подписку до релиза и grace период закончился до даты релиза минус 180 дней
                    if lpt + timedelta(days=grace_period) < release_date - timedelta(days=tfhp):
                        return False
                    # отменившие подписку уже после релиза
                    if release_date < lpt + timedelta(days=21+grace_period) < release_date + timedelta(days=(21+tfhp)):
                        return True if release_date + timedelta(days=tfhp) > now else False

        return True

    seen_by_me = None

    def set_seen(self):
        """Отмечает в таблице TourSeen, что текущий юзер посмотрел этот тур только что.
        Если юзер не авторизован, то отрывает ноги одному байкеру."""
        if not current_user.is_authenticated:
            return
        table = TourSeen.__tablename__
        sql = f'''
            INSERT INTO {table} (tour_id, user_id, seen) VALUES ({self.id}, {current_user.id}, now())
            ON CONFLICT ON CONSTRAINT tours_seen_pkey DO
            UPDATE SET seen = now() WHERE {table}.tour_id = {self.id} AND {table}.user_id = {current_user.id}
            '''
        db.session.execute(sql)
        db.session.commit()
        self.seen_by_me = TourSeen(tour_id=self.id, user_id=current_user.id, seen=datetime.now())


class TourFeature(db.Model):
    """
    Фичи туров.
    """
    __tablename__ = 'tour_features'

    tour_id = db.Column(db.Integer, db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False,
                        primary_key=True)
    feature = db.Column(db.String(32), nullable=False, primary_key=True, index=True)


class TourGalleryTag(db.Model):
    """
    Теги для галереи.
    """
    __tablename__ = 'gallery_tags'

    tour_id = db.Column(db.Integer, db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False,
                        primary_key=True)
    tag = db.Column(db.String(32), nullable=False, primary_key=True, index=True)


class TourPaidFeature(db.Model):
    """
    Платные фичи тура.
    """
    __tablename__ = 'tour_paid_features'

    tour_id = db.Column(db.Integer, db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False,
                        primary_key=True)
    feature = db.Column(db.String(32), nullable=False, primary_key=True, index=True)
    paid_till = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)


class TourBuilderStat(db.Model):
    """
    Статистика работы сборщика туров
    """
    __tablename__ = 'tour_builder_stats'

    id = db.Column(db.Integer(), primary_key=True)
    footage_id = db.Column(db.Integer, db.ForeignKey('footages.id', ondelete='SET NULL', onupdate='CASCADE'),
                           nullable=True)
    started = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    finished = db.Column(db.DateTime(timezone=True))

    user_id = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'), nullable=True)
    cnt_skyboxes = db.Column(db.Integer())  # Количество скайбоксов
    wurst_cutter_time = db.Column(db.Integer())  # Сколько времени нарезались панорамы
    model_worker_actions = db.Column(ARRAY(db.String(32), zero_indexes=True))  # Аргументы вызова низподоха
    model_worker_time = db.Column(db.Integer())  # Время работы обработчика моделей
    model_worker_meshtransform_time = db.Column(db.Integer())  # Время работы низкополигонализатора
    model_worker_texturing_time = db.Column(db.Integer())  # Время работы доллхаусизатора
    model_worker_texturesplit_time = db.Column(db.Integer())  # Время работы texturesplit
    model_worker_exit_code = db.Column(db.Integer())  # Код завершения обработчика моделей
    model_size_before = db.Column(db.Integer())  # Вес модели до обработки
    model_size_after = db.Column(db.Integer())  # Вес модели после обработки
    model_objects_before = db.Column(db.Integer())  # Количество объектов в модели до обработки
    model_objects_after = db.Column(db.Integer())  # Количество объектов в модели до обработки
    model_faces_before = db.Column(db.Integer())  # Количество полигонов модели до обработки
    model_faces_after = db.Column(db.Integer())  # Количество полигонов модели после обработки
    result = db.Column(db.Boolean())
    build_errors = db.Column(JSONB)  # Сюда запишутся meta._loading.build_errors

    footage = db.relationship('Footage', backref='stats')
    user = db.relationship('User')


class TourCheckerBase:
    """
    Проверятор туров на ошибки. При вызове конструктора с files=True также ходит по
    директории тура и проверяет файлы на вшивость.
    """

    def __init__(self, tour, files=False):
        self.tour = tour
        self.footage = tour.footage
        self.files = files
        self.errors = []

    def error(self, text):
        self.errors.append(text)

    @staticmethod
    def check_coord(x):
        return type(x) == list and len(x) == 3

    @staticmethod
    def check_quaternion(q):
        return type(q) == list and len(q) == 4

    def check(self):
        pass


class TourCheckerInside(TourCheckerBase):
    """
    Проверятор традиционных туров (real, virtual) на ошибки.
    """

    def check(self):
        if self.files and not self.footage.files:
            self.errors.append('Нет директории с файлами съёмки')
            self.files = False
        if self.footage.status not in ('testing', 'published', 'banned'):
            return []

        try:
            self.check_resolutions()
            self.check_floors()
            self.check_skyboxes()
            self.check_model()
        except Exception as e:
            self.errors.append('Тур настолько кривой, что даже алгоритм проверки упал его проверяючи: %s.' % str(e))

        return self.errors

    def _check_tour_file(self, filename):
        return os.path.isfile(os.path.join(self.tour.files.abs_path, filename))

    def _check_footage_file(self, filename):
        return os.path.isfile(os.path.join(self.footage.files.abs_path, filename))

    def check_resolutions(self):
        if not self.footage.meta.get('resolutions'):
            self.error('Не определены разрешения')
            return

        if self.files:
            for res in self.footage.meta['resolutions']:
                if not os.path.isdir(os.path.join(self.footage.files.abs_path, str(res))):
                    self.error('Не удалось найти директорию с панорамами %s' % str(res))

    def check_floors(self):
        if not self.footage.meta.get('floors'):
            self.error('Не определены этажи')
            return

        if self.files:
            for floor_id, floor in self.footage.meta['floors'].items():
                if not floor:
                    continue
                if 'small' in floor and not self._check_footage_file(floor['small']):
                    self.error('Не найдена маленькая планировка "%s" для этажа %s' % (floor['small'], str(floor_id)))
                if 'big' in floor and not self._check_footage_file(floor['big']):
                    self.error('Не найдена большая планировка "%s" для этажа %s' % (floor['big'], str(floor_id)))

    def check_skyboxes(self):
        if not self.footage.meta.get('skyboxes'):
            self.error('Не определены скайбоксы')
            return

        no_floors = []
        for box_id, box in self.footage.meta['skyboxes'].items():
            if 'floor' not in box:
                no_floors.append(box_id)
            elif str(box['floor']) not in self.footage.meta.get('floors', {}):
                self.error('У скайбокса %s определён этаж %s, который отсутствует в списке этажей.' %
                           (str(box_id), box['floor']))

            if 'pos' not in box:
                self.error('У скайбокса %s не задана координата (pos)' % str(box_id))
            elif not self.check_coord(box['pos']):
                self.error('У скайбокса %s неверно задана координата (ожидается массив из 3 элементов)' % str(box_id))

            if 'q' not in box:
                self.error('У скайбокса %s не задан кватернион' % str(box_id))
            elif not self.check_quaternion(box['q']):
                self.error('У скайбокса %s неверно задан кватернион (ожидается массив из 4 элементов)' % str(box_id))

            if self.files and self.footage.meta.get('resolutions'):
                for res in self.footage.meta.get('resolutions'):
                    for edge in range(6):
                        file = '%s/%s-%d.jpg' % (res, box_id, edge)
                        abs_file = os.path.join(self.footage.files.abs_path, file)
                        if not os.path.isfile(abs_file):
                            self.error('У скайбокса %s не найден файл с гранью %s' % (str(box_id), file))
                        else:
                            with Image.open(abs_file) as img:
                                if img.size[0] != res and img.size[1] != res:
                                    self.error(
                                        'Разрешение грани %s не соответствует ожидаемому: %s x %s вместо %s x %s' %
                                        (file, str(img.size[0]), str(img.size[1]), str(res), str(res))
                                    )

        if no_floors:
            self.error('Не определён этаж у скайбоксов %s' % ', '.join(sorted(no_floors)))

        if not self.tour.meta.get('start') or type(self.tour.meta.get('start')) != dict:
            self.error('Не определена стартовая точка')
        else:
            start = self.tour.meta['start']
            if str(start.get('skybox')) not in self.footage.meta['skyboxes']:
                self.error('Стартовая точка ссылается на скайбокс "%s", которого нет' % str(start.get('skybox')))
            if not self.check_quaternion(start.get('q')):
                self.error('Неверно задан кватернион стартовой точки')

        if not self.footage.meta.get('passways'):
            self.error('Не найден граф достижимости (passways)')

    def check_model(self):
        if not self.footage.meta.get('model'):
            self.error('Нет модели')
            return

        if self.files:
            if not self._check_footage_file(self.footage.meta['model']):
                self.error('Недоступен файл с моделью %s' % self.footage.meta['model'])

        if not self.footage.meta.get('model_size'):
            self.error('Не вычислен вес модели')

        if not self.footage.meta.get('model_size_gz'):
            self.error('Не вычислен вес модели в gzip')

        if self.files and self.footage.meta.get('mtl'):
            mtl = os.path.join(self.footage.files.abs_path, self.footage.meta['mtl'])
            if not os.path.isfile(mtl):
                self.error('Недоступен файл MTL %s' % self.footage.meta['mtl'])
            else:
                model_dir = os.path.dirname(mtl)
                with open(mtl) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        words = line.split()
                        if words[0].startswith('map_') and not os.path.isfile(os.path.join(model_dir, words[-1])):
                            self.error('Не найден файл %s, на который ссылается MTL (%s)' % (words[-1], line))


class TourCheckerOutside(TourCheckerBase):
    """
    Проверятор outside-туров (real, virtual) на ошибки.
    """

    def check(self):
        if self.files and not self.footage.files:
            self.errors.append('Нет директории с файлами тура или съёмки')
            self.files = False
        if self.footage.status not in ('testing', 'published', 'banned'):
            return []

        try:
            self.check_resolutions()
            self.check_sets()
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            self.errors.append('Тур настолько кривой, что даже алгоритм проверки упал его проверяючи: %s.' % str(e))

        return self.errors

    def check_resolutions(self):
        if 'resolutions' not in self.footage.meta:
            self.error('Не определены разрешения.')
            return
        for res in self.footage.meta['resolutions']:
            if type(res) != list and len(res) != 2:
                self.error('Неверное разрешение {}'.format(res))

    def check_sets(self):
        if 'sets' not in self.footage.meta:
            self.error('В метаданных съёмки отсутствуют сеты.')
            return

        has_start = None
        for set_id, set in self.footage.meta['sets'].items():
            if 'sort' not in set:
                self.error('Найден сет без sort.')
                continue

            if set.get('is_start'):
                if has_start is None:
                    has_start = set_id
                else:
                    self.error('Несколько стартовых сетов: {} и {}'.format(has_start, set_id))

            if 'frames' not in set:
                self.error('У сета {} нет фреймов.'.format(set_id))
            else:
                self.check_frames(set['frames'], set_id)

            if self.files and not os.path.isdir(self.footage.in_files('frames/{}'.format(set_id))):
                self.error('Не найдена директория сета {}'.format(set_id))

        if has_start is None:
            self.error('Ни один сет не помечен как стартовый.')

    def check_frames(self, frames, set_id):
        for frame_id, frame in frames.items():
            if 'pos' not in frame or not self.check_coord(frame['pos']):
                self.error('У фрейма {}/{} отсутствует или неверная координата (pos).'.format(set_id, frame_id))
            if 'angle' not in frame or not self.check_coord(frame['angle']):
                self.error('У фрейма {}{} отсутствует или неверно задан угол камеры (angle).'.format(set_id, frame_id))
            if 'fov' not in frame:
                self.error('У фрейма {}{} не задан FOV.'.format(set_id, frame_id))

            if self.files:
                for res in self.footage.meta.get('resolutions', []):
                    frame_filename = 'frames/{}/{}x{}/{}.jpg'.format(set_id, res[0], res[1], frame_id)
                    if not os.path.isfile(self.footage.in_files(frame_filename)):
                        self.error('Не читается файл {}'.format(frame_filename))

                    with Image.open(self.footage.in_files(frame_filename)) as img:
                        if img.size[0] != res[0] and img.size[1] != res[1]:
                            self.error('Разрешение фрейма {}/{} не соответствует ожидаемому: {}x{} вместо {}x{}'.format(
                                set_id, frame_id, img.size[0], img.size[1], res[0], res[1]
                            ))


class TourUploader(object):
    """
    Загрузчик фототуров
    """

    def __init__(self, job):
        self.url_uploader = current_app.config.get('PHOTO_LOADER_URL')
        self.__status = None
        self.__health = True
        self.__errors = []

        self.position = None
        self.ETA = None
        self.process_time = None
        self.completed = None

        if job is None or job == '':
            self.__set_errors(['Идентификатор загрузки пустой', ])
        else:
            self.job = str(job)

    def __set_errors(self, messeges):
        self.__status = 'error'
        self.__health = False
        self.__errors = messeges
        self.__response = {'status': 'error', 'messages': messeges}

    def __post(self, type):
        url = requests.compat.urljoin(self.url_uploader, type)
        try:
            response = requests.post(url, data={'job': self.job}, timeout=2)
        except requests.exceptions.Timeout:
            self.__set_errors(['Превышен лимит ожидания ответа от api', ])
            return

        if response.status_code != 200:
            self.__set_errors(['Нет соединения с сервером (url:{}, method:{}, status:{})'.format(url,
                                                                                                 'POST',
                                                                                                 response.status_code), ])
        else:
            params = response.json()
            self.__status = params.get('status', 'error')
            if self.__status == 'error':
                self.__set_errors(params.get('messages', ['Неизвесная ошибка', ]))
            else:
                self.__status = params.get('status', 'error')
                self.position = params.get('position')
                self.ETA = params.get('ETA')
            if self.__status == 'cancel' or self.__status == 'delete':
                self.__health = False

    def __set_status(self):
        url = requests.compat.urljoin(self.url_uploader, 'status')
        try:
            response = requests.get(url, params={'job': self.job}, timeout=2)
        except requests.exceptions.Timeout:
            self.__set_errors(['Превышен лимит ожидания ответа от api', ])
            return

        if response.status_code != 200:
            self.__set_errors(['Нет соединения с сервером (url:{}, method:{}, status:{})'.format(url,
                                                                                                 'POST',
                                                                                                 response.status_code), ])
            self.__response = {'status': 'error', 'messages': self.__errors}
        else:
            params = response.json()
            self.__status = params.get('status', 'error')
            if self.__status == 'error':
                self.__set_errors(params.get('messages', []))
            self.position = params.get('position')
            self.process_time = params.get('process_time')
            self.completed = params.get('completed')
            self.complete = params.get('complete')
            self.ETA = params.get('ETA')
            self.__response = params

    @property
    def status(self):
        self.__set_status()
        return self.__response

    @property
    def health(self):
        return self.__health

    @property
    def errors(self):
        return self.__errors

    def start(self):
        self.__post('start')

    def cancel(self):
        self.__post('cancel')

    def delete(self):
        self.__post('delete')


class ToursChangedJurisdiction(db.Model):
    """Юрисдикция тура
    """
    __tablename__ = 'tours_changed_jurisdiction'

    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    local_id = db.Column(db.Integer(), primary_key=True, nullable=False)
    remote_id = db.Column(db.Integer(), nullable=False)
    moved_to = db.Column(db.Text(), nullable=False)


class TourSeen(db.Model):
    """Время последнего просмотра тура пользователем
    """
    __tablename__ = 'tours_seen'

    tour_id = db.Column(db.Integer, db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True)
    seen = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)

    def __repr__(self):
        return f'<TourSeen {self.tour_id}-{self.user_id}: {self.seen}>'


class TourVideo(db.Model):
    """Видеоклипы, снятые по турам
    """
    __tablename__ = 'tour_videos'

    id = db.Column(db.Integer(), primary_key=True)
    tour_id = db.Column(db.Integer, db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    walk = db.Column(db.String(32), nullable=False, default='auto', server_default='auto')
    duration = db.Column(db.Integer)
    size = db.Column(db.Integer)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    fps = db.Column(db.Integer)
    title = db.Column(db.String(256))

    video_s3_key = db.Column(db.String(255))
    preview_s3_key = db.Column(db.String(255))

    user = db.relationship('User', foreign_keys=[user_id])
    tour = db.relationship('Tour', foreign_keys=[tour_id])

    @property
    def url(self):
        return current_app.config['S3_URL'].format(s3_key=self.video_s3_key)

    @property
    def preview(self):
        return current_app.config['S3_URL'].format(s3_key=self.preview_s3_key)

    def api_repr(self, **kwargs):
        d = {
            **{
                'id': self.id,
                'tour_id': self.tour_id,
                'user_id': self.user_id,
                'created': self.created.isoformat(),
                'walk': self.walk,
                'duration': self.duration,
                'size': self.size,
                'width': self.width,
                'height': self.height,
                'fps': self.fps,
                'title': self.title,
                'preview': self.preview,
                'url': self.url,
            },
            **kwargs
        }

        return d

    def update_from_api_request(self, payload):
        """
        Обновляет свои свойства из тела запроса API в `payload`. Проверяет их на валидность и выбрасывает
        abort(400).
        :param payload: dict {walk, duration, size, width, height, fps, title, preview_s3_key, video_s3_key}
        :return: None
        """

        if 'walk' in payload:
            if payload['walk'] not in ('default', 'auto'):
                abort(400, gettext('Bad route ID.'))
            self.walk = payload['walk']

        fields = {
            'duration': int, 'size': int, 'width': int, 'height': int, 'fps': int,
            'title': str, 'video_s3_key': str, 'preview_s3_key': str
        }
        for prop, coerce in fields.items():
            if prop in payload:
                if payload[prop] is None:
                    setattr(self, prop, None)
                else:
                    try:
                        setattr(self, prop, coerce(payload[prop]))
                    except VALIDATION_EXCEPTIONS:
                        abort(400, gettext('Malformed %(key)s value.', key=prop))
