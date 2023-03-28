import os
import io
import shutil
import time
import uuid
import datauri

from flask import abort
from flask_babel import gettext
import mutagen.mp3
from sqlalchemy.orm.attributes import flag_modified

from visual.util import unlink_calm, get_flow_file, downsize_img, coerce_str_i18n
from visual.core import db
from .meshes import ActiveMesh
from .overlays import Overlay
from .actions import Action


class TourMetaInside:
    def __init__(self, tour):
        self.tour = tour

        self.skyboxes = {}
        self.start = {}
        self.languages = None
        self.default_lang = None
        self.actions = {}
        self.blotch = None
        self.splash = None
        self.branding = None
        self.overlays = {}
        self.active_meshes = {}
        self.audio = {}
        self.walk = None
        self.navigator = []
        self.toolbar = None
        self.options = None

        # Сюда кладутся нераспознанные данные из tour.meta
        self.misc = {}

        for key, value in tour.meta.items():
            if key == 'audio':
                self.audio = {}
                for clip_id, clip_data in value.items():
                    self.audio[clip_id] = AudioClip(self, clip_id, clip_data)
            elif key == 'branding':
                self.branding = Branding(self, value)
            elif key == 'overlays':
                self.overlays = {}
                for overlay_id, overlay_data in value.items():
                    self.overlays[overlay_id] = Overlay.from_meta(self, overlay_id, overlay_data)
            elif key == 'active_meshes':
                self.active_meshes = {}
                for mesh_id, mesh_data in value.items():
                    self.active_meshes[mesh_id] = ActiveMesh.from_meta(self, mesh_id, mesh_data)
            elif key == 'navigator':
                for elem in value:
                    self.navigator.append(NavigatorElement(self, elem))
            elif key == 'actions':
                for action_id, action_data in value.items():
                    self.actions[action_id] = Action.create(data=action_data)
            elif key in ('skyboxes', 'start', 'languages', 'default_lang', 'blotch', 'splash', 'overlays', 'active_meshes', 'walk', 'toolbar', 'options'):
                setattr(self, key, value)
            else:
                self.misc[key] = value

    def save_navigator(self):
        """Сохраняет self.navigator в self.tour.meta"""
        if not self.navigator:
            self.tour.meta.pop('navigator', None)
            return
        self.tour.meta['navigator'] = []
        for elem in self.navigator:
            self.tour.meta['navigator'].append(elem.api_repr())

    def save_overlays(self, to_db=False):
        """Сохраняет self.overlays в self.tour.meta"""
        if not self.overlays:
            self.tour.meta.pop('overlays', None)
        else:
            self.tour.meta['overlays'] = {}
            for overlay_id, overlay in self.overlays.items():
                self.tour.meta['overlays'][overlay_id] = overlay.api_repr()
        if to_db:
            flag_modified(self.tour, 'meta')
            db.session.commit()

    def save_active_mesh(self, to_db=False):
        """Сохраняет self.active_meshes в self.tour.meta"""
        if not self.active_meshes:
            self.tour.meta.pop('active_meshes', None)
        else:
            self.tour.meta['active_meshes'] = {}
            for mesh_id, mesh in self.active_meshes.items():
                self.tour.meta['active_meshes'][mesh_id] = mesh.api_repr()
        if to_db:
            flag_modified(self.tour, 'meta')
            db.session.commit()

    def save_actions(self, to_db=False):
        """Сохраняет self.actions в self.tour.meta"""
        if not self.actions:
            self.tour.meta.pop('actions', None)
        else:
            self.tour.meta['actions'] = {}
            for action_id, action in self.actions.items():
                self.tour.meta['actions'][action_id] = action.api_repr()
        if to_db:
            flag_modified(self.tour, 'meta')
            db.session.commit()

    def next_overlay_id(self):
        i = 0
        for k in self.overlays.keys():
            try:
                i = int(k)
            except:
                pass
        i += 1
        return str(i)

    def next_action_id(self):
        i = 0
        for k in self.actions.keys():
            try:
                i = int(k)
            except:
                pass
        i += 1
        return str(i)

    def audioclip_delete(self, clip_id):
        """Удаляет аудиоклип clip_id и его упоминания в скайбоксах"""
        if clip_id not in self.audio:
            raise KeyError('No audioclip {}'.format(clip_id))

        # Убираем из скайбоксов упоминания о клипе:
        for skybox in self.skyboxes.values():
            if skybox.audio and clip_id in skybox.audio:
                skybox.audio.pop(clip_id, None)

        self.audio[clip_id].delete_files()


class TourSkybox:
    def __init__(self, meta, skybox_id, data):
        self.meta = meta
        self.id = skybox_id

        self.title = data.get('title')
        self.disabled = data.get('disabled')
        self.audio = data.get('audio')

    def api_repr(self):
        """Отдаёт скайбокс в виде словаря для ответа API."""
        r = {prop: getattr(self, prop) for prop in ('title', 'disabled') if getattr(self, prop, None) is not None}
        if self.disabled:
            r['disabled'] = self.disabled
        if self.audio:
            r['audio'] = self.audio
        return r


class AudioClip:
    TRACK_SIZE_LIMIT = 100*1024*1024

    def __init__(self, meta, clip_id, data):
        self.meta = meta
        self.id = clip_id

        self.url = data.get('url')
        self.title = data.get('title')
        self.volume = data.get('volume')
        self.loop = data.get('loop')
        self.pause = data.get('pause')
        self.revision = data.get('revision')
        self.filesize = data.get('filesize')
        self.duration = data.get('duration')

    def api_repr(self):
        """Отдаёт клип в виде словаря для ответа API."""
        r = {prop: getattr(self, prop) for prop in ('url', 'title', 'volume', 'loop', 'pause', 'revision', 'filesize', 'duration') if getattr(self, prop, None) is not None}
        return r

    def __repr__(self):
        return '<AudioClip #{0.id} "{0.url}">'.format(self)

    def delete_files(self):
        """Удаляет свои файлы."""
        if self.url:
            unlink_calm(self.meta.footage.in_files(self.url))

    def set_mp3(self, src):
        """Использовать в качестве дорожки файл src.
        Проверяет src, считает его размер и длительность, копирует в ассеты и устанавливает url, revision, filesize, duration.
        @todo: не стирает предыдущий файл. Бладодаря этому, при перезаливке файла с тем же именем, что был в стёртой дорожке, revision всё равно увеличится, но остаётся мусор на диске.
        :raises HTTPException"""
        filename = os.path.basename(src)
        self.meta.tour.mkdir()
        dst = os.path.join(self.meta.tour.in_files('audio', filename))

        # Проверяем расширение
        if src[-4:].lower() != '.mp3':
            abort(400, gettext('%(filename)s: should be an MP3 file.', filename=filename))

        # Если файл с таким именем уже есть, увеличиваем revision
        if os.path.isfile(dst):
            self.revision = (self.revision or 0) + 1

        # Прверяем размер файла
        self.filesize = os.stat(src).st_size
        if self.filesize > self.TRACK_SIZE_LIMIT:
            abort(400, gettext('%(filename)s is too large. Limit: %(limit)d MB.', filename=filename, limit=round(self.TRACK_SIZE_LIMIT / 1024 / 1024)))

        # Проверяем валидность и считаем длительность
        try:
            mp3 = mutagen.mp3.MP3(src)
        except mutagen.mp3.HeaderNotFoundError:
            abort(400, gettext('%(filename)s: not a valid MP3 file.', filename=filename))
        self.duration = mp3.info.length

        os.makedirs(self.meta.tour.in_files('audio'), exist_ok=True)
        shutil.move(src, dst)
        self.url = 'audio/' + filename


class Branding:
    def __init__(self, meta, data=None):
        self.meta = meta
        if data is None:
            data = {}

        self.copyright_map = data.get('copyright_map')
        self.copyright_help = data.get('copyright_help')
        self.logo_help = data.get('logo_help')
        self.logo_help_link = data.get('logo_help_link')
        self.watermark = data.get('watermark')
        

    def api_repr(self):
        """Отдаёт объект в виде словаря для ответа API."""
        r = {prop: getattr(self, prop) for prop in ('copyright_map', 'copyright_help', 'logo_help', 'logo_help_link', 'watermark') if getattr(self, prop, None) is not None}
        return r

    def __repr__(self):
        return '<Branding>'

    def gen_filename(self, ext):
        """Генерит новое имя для логотипа: {huinia}.{ext}"""
        ext = ext.lstrip('.')
        return '{}.{}'.format(time.time(), ext)


class NavigatorElement:
    def __init__(self, meta, data=None):
        self.meta = meta
        if data is None:
            data = {}

        self.img = data.get('img')
        self.skybox = data.get('skybox')
        self.q = data.get('q')
        self.title = data.get('title')

    def api_repr(self):
        """Отдаёт объект в виде словаря для ответа API."""
        r = {prop: getattr(self, prop) for prop in ('img', 'skybox', 'q', 'title') if getattr(self, prop, None) is not None}
        return r

    def __repr__(self):
        return '<Navigator skybox={o.skybox}>'.format(o=self)

    def set_img(self, src):
        """Загружает картинку из src. Генерит ей новое имя (UUID), сохраняя расширение.
        Если была старая картинка, удаляет её.
        :param src:
        :return:
        """
        _, ext = os.path.splitext(src)
        filename = str(uuid.uuid4()).replace('-', '') + ext

        self.meta.tour.mkdir()
        dst = os.path.join(self.meta.tour.in_files('navigator', filename))

        if self.img and self.meta.tour.files:
            unlink_calm(self.meta.tour.in_files(self.img))

        os.makedirs(self.meta.tour.in_files('navigator'), exist_ok=True)
        shutil.copy(src, dst)
        self.img = 'navigator/' + filename

    def delete_files(self):
        """Удаляет свои файлы."""
        if self.img and self.meta.tour.files:
            unlink_calm(self.meta.tour.in_files(self.img))

    def update_from_api_request(self, payload):
        def _get_size(val):
            """Проверяет тип свойства тела запроса с размером и возвращает его в виде списека [int, int]"""
            try:
                size = (int(val[0]), int(val[1]))
            except (KeyError, ValueError):
                abort(400, gettext('Bad data type for property %(property)s', property='big@resize'))
            return size

        warnings = []
        simple_props = {'img': str, 'skybox': str, 'title': coerce_str_i18n}
        skip_props = {'img@resize'}

        if 'skybox' not in payload:
            abort(400, gettext('No skybox specified when creating navigator element.'))

        for key, value in payload.items():
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, simple_props[key](value))
                    except TypeError:
                        abort(400, gettext('Bad data type for property %(property)s', property=key))

            elif key == 'q':
                try:
                    self.q = [float(value[i]) for i in range(4)]
                except (ValueError, KeyError, TypeError, IndexError):
                    abort(400, gettext('Bad data type for property %(property)s', property=key))

            elif key == 'img@flow':
                if 'img@dataurl' in payload:
                    abort(400, gettext('You can not specify %(key1)s and %(key2)s simultaneously in one request.', key1='img@flow', key2='img@dataurl'))

                src, _, _ = get_flow_file(payload, 'img@flow')
                _, ext = os.path.splitext(src)
                filename = str(uuid.uuid4()).replace('-', '') + ext

                self.meta.tour.mkdir()
                os.makedirs(self.meta.tour.in_files('navigator'), exist_ok=True)
                dst = os.path.join(self.meta.tour.in_files('navigator', filename))
                if self.img:
                    unlink_calm(self.meta.tour.in_files(self.img))

                if 'img@resize' in payload:
                    downsize_img(src, dst, _get_size(payload['img@resize']), 'fit', True)
                else:
                    shutil.copy(src, dst)

                self.img = 'navigator/' + filename

            elif key == 'img@dataurl':
                if 'img@flow' in payload:
                    abort(400, gettext('You can not specify %(key1)s and %(key2)s simultaneously in one request.', key1='img@dataurl', key2='img@flow'))

                try:
                    uri = datauri.DataURI(value)
                except ValueError:
                    abort(400, gettext('Malformed %(key)s value.', key=key))

                mimetypes = {
                    'image/jpeg': '.jpg',
                    'image/png': '.png'
                }
                if uri.mimetype not in mimetypes:
                    abort(gettext('Unknown image type in %(key)s.', key=key))
                filename = str(uuid.uuid4()).replace('-', '') + mimetypes[uri.mimetype]

                self.meta.tour.mkdir()
                os.makedirs(self.meta.tour.in_files('navigator'), exist_ok=True)
                dst = os.path.join(self.meta.tour.in_files('navigator', filename))
                if self.img:
                    unlink_calm(self.meta.tour.in_files(self.img))

                if 'img@resize' in payload:
                    src = io.BytesIO(uri.data)
                    downsize_img(src, dst, _get_size(payload['img@resize']), 'fit', True)
                    src.close()
                else:
                    with open(dst, 'wb') as fh:
                        fh.write(uri.data)

                self.img = 'navigator/' + filename

            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

        return warnings
