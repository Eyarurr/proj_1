import os
import re
from PIL import Image

from flask_babel import gettext

from visual.util import unlink_calm
from . import MetaUrl


class FootageMetaInside:
    def __init__(self, footage):
        self.footage = footage

        self.resolutions = []
        self.floors = {}
        self.skyboxes = {}
        self.binocular = False
        self.model = MetaUrl()
        self.model_revision = None
        self.model_size = None
        self.model_size_gz = None
        self.mtl = None
        self.passways = None
        self.shadows = {}
        self._loading = None
        self._queued = None
        self._processing = None

        # Сюда кладутся нераспознанные данные из footage.meta
        self.misc = {}

        for key, value in footage.meta.items():
            if key == 'floors':
                for floor_id, floor_data in value.items():
                    self.floors[floor_id] = Floor(self, floor_id, floor_data)
            elif key == 'skyboxes':
                for skybox_id, skybox_data in value.items():
                    self.skyboxes[skybox_id] = FootageSkybox(self, skybox_id, skybox_data)
            elif key == 'shadows':
                for shadow_id, shadow_data in value.items():
                    self.shadows[shadow_id] = Shadow(self, shadow_id, shadow_data)
            elif key in ('resolutions', 'binocular', 'model', 'model_revision', 'model_size', 'model_size_gz', 'mtl', 'passways', '_loading', '_queued', '_processing'):
                setattr(self, key, value)
            else:
                self.misc[key] = value

    def max_res(self):
        return max(self.resolutions, default=None)

    def skybox_delete(self, skybox_id):
        """Удаляет скайбокс skybox_id"""
        if skybox_id not in self.skyboxes:
            raise KeyError('No skybox {}'.format(skybox_id))
        self.skyboxes[skybox_id].delete_files()
        self.skyboxes.pop(skybox_id)


class Floor:
    def __init__(self, meta, floor_id, data):
        self.meta = meta
        self.id = floor_id

        self.big = data.get('big')
        self.small = data.get('small')
        self.title = data.get('title')
        self.offset = data.get('offset')
        self.scale = data.get('scale')

    def api_repr(self):
        """Отдаёт этаж в виде словаря для ответа API."""
        r = {prop: getattr(self, prop) for prop in ('big', 'small', 'title', 'offset', 'scale') if getattr(self, prop, None) is not None}
        return r

    def __repr__(self):
        return '<Floor #{0.id} "{0.title}">'.format(self)

    PLAN_FILENAME_PATTERN = r'(\d+)-(big|small)-(\d+)\.(jpg|jpeg|png)$'

    def gen_plan_filename(self, variant, ext='jpg'):
        """Генерит новое имя для файла с планировкой: {floor_id}-{variant}-{revision}.jpg (1-big-12.{ext})"""
        ext = ext.lstrip('.')
        revision = 0
        if variant == 'big':
            if self.big:
                m = re.search(self.PLAN_FILENAME_PATTERN, self.big)
                if m:
                    revision = int(m.group(3)) + 1
        elif variant == 'small':
            if self.small:
                m = re.search(self.PLAN_FILENAME_PATTERN, self.small)
                if m:
                    revision = int(m.group(3)) + 1
        else:
            raise ValueError('Floor.gen_plan_filename() variant parameter should be `small` or `big`.')

        return '{}-{}-{}.{}'.format(self.id, variant, revision, ext)

    def delete_files(self):
        """Удаляет файлы планировок."""
        if self.big:
            unlink_calm(self.meta.footage.in_files(self.big))

        if self.small:
            unlink_calm(self.meta.footage.in_files(self.small))


class FootageSkybox:
    def __init__(self, meta, skybox_id, data):
        self.meta = meta
        self.id = skybox_id
        self.pos = data.get('pos')
        self.q = data.get('q')
        self.floor = data.get('floor')
        self.files_size = data.get('files_size', {})
        self.title = data.get('title')
        self.revision = data.get('revision')
        self.disabled = data.get('disabled')
        self.audio = data.get('audio')
        self.markerZ = data.get('markerZ')
        self.shadows = data.get('shadows')

    def api_repr(self):
        """Отдаёт скайбокс в виде словаря для ответа API."""
        r = {
            prop: getattr(self, prop)
            for prop in ('pos', 'q', 'floor', 'files_size', 'title', 'revision', 'disabled', 'audio', 'markerZ', 'shadows')
            if getattr(self, prop, None) is not None
        }
        return r

    def __repr__(self):
        return '<Skybox "{0.id}">'.format(self)

    def wurst_hacken(self, wurst, eye='center', render_type='vray', jpeg_quality=85, shadow=None):
        """
        Нарезает грани скайбокса из отрендерённой колбасы. Кладёт файлы в нужные директории, добавляет скайбокс в мету.
        Считает размер файлов в self.files_size. Увеличивает self.revision, если перезаписался хоть один файл
        :param wurst: Путь к колбасе
        :param eye: Глаз: center, left, right, both
        :param render_type: vray, corona
        :param jpeg_quality: качество сжатия JPEG
        :param shadow: в какую тень резать панорамы
        :raises ValueError
        """
        if eye not in ('center', 'left', 'right', 'both'):
            raise ValueError('Wrong value for eye parameter.')

        if not self.meta.resolutions:
            raise ValueError('No resolutions defined in footage.')

        # Номер куска в колбасе: (номер грани куба, transpose, rotate)
        render_rules = {
            'vray': {
                0: (2, Image.FLIP_LEFT_RIGHT, None),
                1: (0, Image.FLIP_LEFT_RIGHT, None),
                2: (4, Image.FLIP_TOP_BOTTOM, -90),
                3: (5, Image.FLIP_TOP_BOTTOM, 90),
                4: (3, Image.FLIP_LEFT_RIGHT, None),
                5: (1, Image.FLIP_LEFT_RIGHT, None),
                6: (2, Image.FLIP_LEFT_RIGHT, None),
                7: (0, Image.FLIP_LEFT_RIGHT, None),
                8: (4, Image.FLIP_TOP_BOTTOM, -90),
                9: (5, Image.FLIP_TOP_BOTTOM, 90),
                10: (3, Image.FLIP_LEFT_RIGHT, None),
                11: (1, Image.FLIP_LEFT_RIGHT, None),
            },
            'corona': {
                0: (1, Image.FLIP_LEFT_RIGHT, None),
                1: (3, Image.FLIP_LEFT_RIGHT, None),
                2: (4, Image.FLIP_TOP_BOTTOM, None),
                3: (5, Image.FLIP_TOP_BOTTOM, None),
                4: (2, Image.FLIP_LEFT_RIGHT, None),
                5: (0, Image.FLIP_LEFT_RIGHT, None),
                6: (1, Image.FLIP_LEFT_RIGHT, None),
                7: (3, Image.FLIP_LEFT_RIGHT, None),
                8: (4, Image.FLIP_TOP_BOTTOM, None),
                9: (5, Image.FLIP_TOP_BOTTOM, None),
                10: (2, Image.FLIP_LEFT_RIGHT, None),
                11: (0, Image.FLIP_LEFT_RIGHT, None),
            }
        }
        if render_type not in render_rules:
            raise ValueError('Unknown render type: %s' % render_type)
        rules = render_rules[render_type]

        max_res = self.meta.max_res()

        # Инициализируем self.files_size
        if shadow:
            files_size = self.files_size.setdefault('shadows', {}).setdefault(shadow, {})
        else:
            files_size = self.files_size
        for res in self.meta.resolutions:
            files_size.setdefault(str(res), {})
            if eye == 'both':
                files_size[str(res)]['left'] = 0
                files_size[str(res)]['right'] = 0
            else:
                files_size[str(res)][eye] = 0

        with Image.open(wurst) as wurst:
            # Проверяем размер колбасы
            n_faces = 12 if eye == 'both' else 6
            if wurst.width < max_res * n_faces or wurst.height < max_res or wurst.width != wurst.height * n_faces:
                message = gettext('Panorama should be at least %(std)s px, you\'ve got %(wrong)s.', std='{:d}x{:d}'.format(
                    max_res * n_faces, max_res), wrong='{:d}x{:d}'.format(wurst.width, wurst.height))
                raise ValueError(message)

            wurst = wurst.convert("RGB")

            # Установится в True, если хотя бы один файл перезаписывает существующий
            had_files = False

            for i in range(n_faces):
                face_id = rules[i][0]
                transpose = rules[i][1]
                rotate = rules[i][2]

                # Вырезаем кусок
                face = wurst.crop([i * wurst.height, 0, (i + 1) * wurst.height, wurst.height])
                if rotate is not None:
                    face = face.rotate(rotate)
                if transpose is not None:
                    face = face.transpose(transpose)

                for res in sorted(self.meta.resolutions, reverse=True):
                    if res != wurst.height:
                        face.thumbnail([res, res], Image.LANCZOS)

                    # Путь, куда класть грань
                    path = []
                    if shadow:
                        path += ['shadows', shadow]
                    path.append(str(res))
                    if eye == 'left' or eye == 'right':
                        path.append(eye)
                    elif eye == 'both':
                        path.append('left' if i < 6 else 'right')
                    os.makedirs(self.meta.footage.in_files(*path), exist_ok=True)

                    # Имя файла грани
                    filename = '{}-{}.jpg'.format(self.id, face_id)

                    dst = self.meta.footage.in_files(*path, filename)
                    if not had_files and os.path.exists(dst):
                        had_files = True

                    face.save(dst, "JPEG", quality=jpeg_quality, optimize=True)

                    # files_size
                    if eye == 'both':
                        size_key = 'left' if i < 6 else 'right'
                    else:
                        size_key = eye
                    files_size.setdefault(str(res), {}).setdefault(size_key, 0)
                    files_size[str(res)][size_key] += os.stat(dst).st_size

            if had_files:
                self.revision = (self.revision or 0) + 1
                if self.meta._loading and 'skyboxes' in self.meta._loading:
                    if str(self.id) in self.meta._loading['skyboxes']:
                        self.meta._loading['skyboxes'][str(self.id)]['revision'] = self.revision

    def delete_files(self):
        """Удаляет все свои файлы."""
        for res in self.meta.resolutions:
            for face_id in range(6):
                unlink_calm(self.meta.footage.in_files(str(res), '{}-{}.jpg'.format(self.id, face_id)))
                for eye in ('left', 'right'):
                    unlink_calm(self.meta.footage.in_files(str(res), eye, '{}-{}.jpg'.format(self.id, face_id)))

    def _skybox_files_size(self, resolution, eye=None, shadow=None):
        """
        Считает суммарный размер 6 граней скайбокса для заданного разрешения, глаза и тени.
        Если хоть один файл не найден, возвращает None
        """
        path = []
        if shadow:
            path = ['shadows', shadow] + path
        path.append(resolution)
        if eye:
            path.append(eye)

        size = 0
        basedir = self.meta.footage.in_files(*path)

        for face in range(6):
            face_path = os.path.join(basedir, '{}-{:d}.jpg'.format(self.id, face))
            try:
                size += os.stat(face_path).st_size
            except FileNotFoundError:
                return None

        return size

    def _get_files_size_entry(self, resolution, shadow=None):
        """Возвращает элемент files_size: {'center': int, 'left': int, 'right': int}."""
        fsize = {}
        s = self._skybox_files_size(resolution, shadow=shadow)
        if s is not None:
            fsize['center'] = s
        if self.meta.binocular:
            s = self._skybox_files_size(resolution, 'left', shadow=shadow)
            if s is not None:
                fsize['left'] = s
            s = self._skybox_files_size(resolution, 'right', shadow=shadow)
            if s is not None:
                fsize['right'] = s
        return fsize

    def recalc_files_size(self):
        """Пересчитывает self.files_sizes."""
        self.files_size = {}
        for res in self.meta.resolutions:
            res = str(res)
            self.files_size[res] = self._get_files_size_entry(res)

            if self.shadows:
                self.files_size.setdefault('shadows', {})
                for shadow in self.shadows:
                    self.files_size['shadows'].setdefault(shadow, {}).setdefault(res, {})
                    self.files_size['shadows'][shadow][res] = self._get_files_size_entry(res, shadow=shadow)


class Shadow:
    EFFECTS = ('fade', )

    def __init__(self, meta, shadow_id, data):
        self.meta = meta
        self.id = shadow_id
        self.title = data.get('title')
        self.disabled = data.get('disabled')
        self.enter = data.get('enter')
        self.multichoice = data.get('multichoice')

    def as_dict(self):
        """Отдаёт тень в виде словаря для ответа API."""
        r = {prop: getattr(self, prop) for prop in ('title', 'disabled', 'enter', 'multichoice') if getattr(self, prop, None) is not None}
        return r

    def __repr__(self):
        return '<Shadow "{0.id}">'.format(self)
