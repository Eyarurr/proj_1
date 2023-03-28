import os
import math
import collections
import phonenumbers
import pytz
import datetime
import urllib.parse
import threading
import colors
import zipfile
import json
import typing
import logging
import shutil

from wtforms import Form, StringField, IntegerField, SelectMultipleField, BooleanField
from wtforms.widgets import FileInput, ListWidget, CheckboxInput
from flask import flash, abort, g, request, Markup, Response, current_app, render_template, redirect, url_for, send_file
from flask import current_app as app
from flask_babel import gettext
from PIL import Image, ImageOps
from flask.views import View
from visual.core import db

from io import StringIO
from html.parser import HTMLParser


class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.text = StringIO()

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()


def strip_html(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()


def flash_errors(form):
    """
    Перетаскивает ошибки из WTF-формы form в flash(..., 'error')
    :param form: Form
    :return:
    """
    for field, errors in form.errors.items():
        for error in errors:
            if app.config['DEBUG']:
                error = '{}: {}'.format(field, error)
            flash(error, 'danger')


def json_errors(form, delim='\n'):
    jar = []
    for field, errors in form.errors.items():
        for error in errors:
            jar.append(error)
    return {"error": delim.join(jar)}


def plural(x, var1, var2, var5=None):
    """
    Спряжение существительных после числительного. Например:
    У вас в штанах {{ x }} {{ x|plural('енотик', 'енотика', 'енотиков') }}
    :param x: количество
    :param var1: 1, 21, 31, ...
    :param var2: 2-4, 22-24, 33-34, ...
    :param var5: 0, 5-9, 10-20, 25-30, 35-40, ...
    :return:
    """
    var5 = var5 or var2
    x = abs(x)
    if x == 0:
        return var5
    if x % 10 == 1 and x % 100 != 11:
        return var1
    elif 2 <= (x % 10) <= 4 and (x % 100 < 10 or x % 100 >= 20):
        return var2
    else:
        return var5


def copy_row(row, ignored_columns=('id', 'created')):
    model = row.__class__
    copy = model()

    for col in row.__table__.columns:
        if col.name not in ignored_columns:
            setattr(copy, col.name, getattr(row, col.name))

    return copy


def test_endpoint(fn):
    """
    Запрещает эндпоинту работать в окружении, отличного от `development`
    :param fn:
    :return:
    """

    def f(*args, **kwargs):
        if app.config['ENV'] != 'development':
            abort(403)
        else:
            return fn(*args, **kwargs)

    return f


metric_prefix = {
    -24: 'йокто',
    -21: 'зепто',
    -18: 'атто',
    -15: 'фемто',
    -12: 'пико',
    -9: 'нано',
    -6: 'микро',
    -3: 'милли',
    0: '',
    3: 'кило',
    6: 'мега',
    9: 'гига',
    12: 'тера',
    15: 'пета',
    18: 'экза',
    21: 'зетта',
    24: 'йотта'
}

metric_prefix_short = {
    -24: 'и',
    -21: 'з',
    -18: 'а',
    -15: 'ф',
    -12: 'п',
    -9: 'н',
    -6: 'мк',
    -3: 'м',
    0: '',
    3: 'К',
    6: 'М',
    9: 'Г',
    12: 'Т',
    15: 'П',
    18: 'Э',
    21: 'З',
    24: 'И'
}


def order(x):
    return int(math.log10(x) / 3) * 3


def human_file_size(x, variant='long'):
    if x < 0:
        return 'отрицательный размер'
    elif x == 0:
        return '0 байт' if variant == 'long' else '0'
    elif x < 1.616229383838e-35:
        return 'размер меньше планковского... проверьте расчёты, коллега'
    elif x < 1:
        bits = int(x * 8)
        return '{} {}'.format(bits, plural(bits, 'бит', 'бита', 'бит'))
    elif x > 1e24:
        return '%.3e байт' % x
    elif x > 1e81:
        return 'размер превышает число атомов во Вселенной'
    else:
        number = round(x / (10 ** order(x)), 1)
        if number == int(number):
            number = int(number)
        if number > 10:
            number = int(number)
        if variant == 'long':
            return '{} {}{}'.format(number, metric_prefix[order(x)], plural(number, 'байт', 'байта', 'байт'))
        else:
            return '{} {}б'.format(number, metric_prefix_short[order(x)])


def normalize_phone(x):
    """
    Приводит нечто похожее на телефонный номер к виду +7 XXX YYY-YY-YY
    Если в x полная хуйня, выбросит ValueError
    :param x:
    :return:
    """
    try:
        phone = phonenumbers.parse(x, 'RU')
        return phonenumbers.format_number(phone, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except phonenumbers.NumberParseException:
        raise ValueError


class PriceField(IntegerField):
    def process_formdata(self, valuelist):
        if len(valuelist) and type(valuelist[0]) is str:
            valuelist[0] = valuelist[0].replace(' ', '')
        super().process_formdata(valuelist)


class PhoneField(StringField):
    def pre_validate(self, form):
        if self.data == '':
            return
        try:
            for x in self.data.split(','):
                phonenumbers.parse(x, 'RU')
        except phonenumbers.NumberParseException:
            self.errors.append('Номер телефона неверен.')

    def process_data(self, value):
        """
        Обрабатывает данные, пришедшие при инициализации формы, вызывается
        в конструкторе формы
        :param value: любой объект
        :return:
        """
        if type(value) is list:
            value = ', '.join([x.strip() for x in value if type(x) is str])
        super().process_data(value)

    def process_formdata(self, valuelist):
        """
        Обрабатывает данные, пришедшие из request
        :param valuelist: список строк
        :return:
        """
        value = ''
        try:
            value = valuelist[0]
            phones = [phonenumbers.parse(x, 'RU') for x in value.split(',')]
            value = ', '.join(
                [phonenumbers.format_number(x, phonenumbers.PhoneNumberFormat.INTERNATIONAL) for x in phones])
        except (IndexError, phonenumbers.NumberParseException):
            pass
        super().process_formdata([value])


class MultipleFileInput(FileInput):
    def __call__(self, field, **kwargs):
        kwargs['multiple'] = True
        return super().__call__(field, **kwargs)


class MultiCheckboxField(SelectMultipleField):
    """
    A multiple-select, except displays a list of checkboxes.

    Iterating the field will produce subfields, allowing custom rendering of
    the enclosed checkbox fields.
    """
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class FiltersForm(Form):
    """
    Для всех полей обязательно нужно указывать default!
    """
    __remember_fields__ = []

    def _cookie_name(self, field):
        return '_filters.' + self.__class__.__name__ + '.' + field

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.__remember_fields__:
            if field not in request.args and self._cookie_name(field) in request.cookies:
                getattr(self, field).data = request.cookies[self._cookie_name(field)]

        for field in self.__remember_fields__:
            defer_cookie(self._cookie_name(field), getattr(self, field).data, max_age=60 * 60 * 24 * 7, path='/')

    @property
    def is_dirty(self):
        # У SelectField'ов без инициализации data == 'None'. Ёбаные вы wtforms!
        for field in self:
            if field.data != field.default:
                return True
        return False

    def as_dict(self, **kwargs):
        """Возвращает словарь со значениями полей формы (фильтров). В kwargs можно переопределить значения полей."""
        d = {field.name: field.data or None for field in self if field.name != 'csrf_token'}
        return {**d, **kwargs}

    @property
    def default_values(self):
        return {
            field.name: None if isinstance(field, BooleanField) else field.default
            for field in self if field.name != 'csrf_token'
        }


class SwitchWidget:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, field, **kwargs):
        form = kwargs.get('form')
        if form:
            d = {k: v for k, v in form.as_dict().items() if v is not None}
        else:
            d = {}

        html = ['<div class="btn-group btn-group-sm">']
        for val, label, selected in field.iter_choices():
            d[field.name] = val
            html.append(
                '<a href="?%s" class="btn btn-sm btn-%s">%s</a>' %
                (urllib.parse.urlencode(d), 'primary' if selected else 'outline-secondary', label)
            )
        html.append('</div>')

        return Markup(''.join(html))


def now():
    return pytz.utc.localize(datetime.datetime.utcnow())


def defer_cookie(*args, **kwargs):
    """
    Запоминает, что перед тем, как отдать Response, нужно установить куку. Параметры те же, что и у Response.set_cookie()
    :param args:
    :param kwargs:
    :return:
    """
    if 'deferred_cookies' not in g:
        g.deferred_cookies = []

    g.deferred_cookies.append((args, kwargs))


def downsize_img(src, dst, size, mode='fit', upscale=False, format=None):
    """Берёт картинку из src (путь или file-like object), ресайзит её до size=(w,h) со стратегией
    'fit' или 'crop', сохраняет в dst (путь или file-like object) или возвращает Image-объект, если dst is None
    """
    img = Image.open(src)
    if mode == 'crop':
        iw, ih = img.size
        width, height = size
        if iw > width or ih > height:
            iaspect = iw / ih
            taspect = width / height
            if iaspect > taspect:
                left = int((iw - ih * taspect) / 2)
                right = iw - left
                crop_rect = (left, 0, right, ih)
            else:
                upper = int((ih - iw / taspect) / 2)
                lower = ih - upper
                crop_rect = (0, upper, iw, lower)

            img = img.crop(crop_rect).resize(size, Image.LANCZOS)
    elif mode == 'fit':
        x, y = img.size
        can_upscale = size[0] > x and size[1] > y
        if x > size[0]:
            y = round(max(y * size[0] / x, 1))
            x = int(size[0])
        if y > size[1]:
            x = round(max(x * size[1] / y, 1))
            y = int(size[1])

        if upscale and can_upscale:
            if size[0] / size[1] < x / y:
                y = round(max(y * size[0] / x, 1))
                x = int(size[0])
            else:
                x = round(max(x * size[1] / y, 1))
                y = int(size[1])

        size = x, y

        if size != img.size:
            img.draft(None, size)
            im = img.resize(size, Image.LANCZOS)

            img.im = im.im
            img.mode = im.mode
            img._size = size

            img.readonly = 0
            img.pyaccess = None

    if img.mode in ('RGBA', 'LA') and dst is not None and dst.lower().endswith('jpg'):
        background = Image.new(img.mode[:-1], img.size, (255, 255, 255))
        background.paste(img, img.split()[-1])
        img = background

    if dst is None:
        return img
    else:
        img.save(dst, format)


def checksize_img(src, size):
    """Берёт картинку из src (путь или file-like object), и проверяет совпадает ли ее размер с size (w,h)
    """
    width, height = size
    img = Image.open(src)
    iw, ih = img.size
    img.close()

    return (width, height) == (iw, ih)


def unlink_calm(file, fail_flash=False):
    """
    Удаляет файл file, но глотает исключения OSError (нет файла, нет прав). Возвращает True, если файл удалился и False, если произошла ошибка.
    Если fail_flash == True, то сообщает о неудаче в flash
    :param file:
    :param fail_flash:
    :return:
    """
    try:
        os.unlink(file)
        return True
    except OSError as e:
        if fail_flash:
            flash('Почему-то не удалось удалить файл %s: %s' % (file, e), 'warning')
        return False


def get_lang():
    if g and g.lang:
        return g.lang
    else:
        return 'en'


def dict_merge(dct, merge_dct):
    """ Recursive dict merge. Inspired by :meth:``dict.update()``, instead of
    updating only top-level keys, dict_merge recurses down into dicts nested
    to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
    ``dct``.
    :param dct: dict onto which the merge is executed
    :param merge_dct: dct merged into dct
    :return: None
    """
    for k, v in merge_dct.items():
        if (k in dct and isinstance(dct[k], dict)
                and isinstance(merge_dct[k], collections.abc.Mapping)):
            dict_merge(dct[k], merge_dct[k])
        else:
            dct[k] = merge_dct[k]


class Quaternion:
    def __init__(self, *args):
        if len(args) == 4:
            self.x = float(args[0])
            self.y = float(args[1])
            self.z = float(args[2])
            self.w = float(args[3])
        elif len(args) == 1:
            src = args[0]
            if type(src) == dict:
                self.x = float(src['x'])
                self.y = float(src['y'])
                self.z = float(src['z'])
                self.w = float(src['w'])
            else:
                raise ValueError('Bad Quaternion init args')
        else:
            raise ValueError('Bad Quaternion init args')

    def as_dict(self):
        return {'x': self.x, 'y': self.y, 'z': self.z, 'w': self.z}

    def as_list(self):
        return [self.x, self.y, self.z, self.w]

    def __mul__(self, that):
        x = self.x * float(that.w) + self.w * float(that.x) + self.y * float(that.z) - self.z * float(that.y)
        y = self.y * float(that.w) + self.w * float(that.y) + self.z * float(that.x) - self.x * float(that.z)
        z = self.z * float(that.w) + self.w * float(that.z) + self.x * float(that.y) - self.y * float(that.x)
        w = self.w * float(that.w) - self.x * float(that.x) - self.y * float(that.y) - self.z * float(that.z)

        return Quaternion(x, y, z, w)

    def __repr__(self):
        return 'Quaternion(%f, %f, %f, %f)' % (self.x, self.y, self.z, self.w)

    @staticmethod
    def _test():
        q1 = Quaternion({"x": 0.000983, "y": 0.003907, "z": -0.741991, "w": 0.670399})
        q2 = Quaternion(0, 0, 0.7071067811865476, 0.7071067811865476)
        q = q1 * q2
        print('%r * %r = %r' % (q1, q2, q))

        q.y, q.z = -q.z, -q.y
        print(q)


class LogPipe(threading.Thread):
    """File-like object, который можно скормить в subprocess.Popen() в качестве stdout или stderr. Отправляет вывод из
    этих потоков в self.logger.info()"""

    def __init__(self, logger):
        """Setup the object with a logger and start the thread
        """
        threading.Thread.__init__(self)
        self.daemon = False
        self.logger = logger
        self.fdRead, self.fdWrite = os.pipe()
        self.pipeReader = os.fdopen(self.fdRead)
        self.process = None
        self.start()

    def fileno(self):
        """Return the write file descriptor of the pipe
        """
        return self.fdWrite

    def run(self):
        """Run the thread, logging everything.
        """
        for line in iter(self.pipeReader.readline, ''):
            self.do_log(line.strip())

        self.pipeReader.close()

    def do_log(self, line):
        """Actual logging.
        """
        self.logger.info(line)

    def close(self):
        """Close the write end of the pipe.
        """
        os.close(self.fdWrite)

    def stop(self):
        self._stop = True
        self.close()

    def __del__(self):
        try:
            self.stop()
        except:
            pass
        try:
            del self.fdRead
            del self.fdWrite
        except:
            pass


def not_cached_response(body):
    resp = Response(body)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


class ModelInfo:
    """
    Информация о модели.
    cnt_vertexes: количество вершин
    cnt_faces: количество полигоов
    objects: Словарь с объектами модели вида {object_name: {'cnt_vertexes': int, 'bb': BoundingBox}, ...}
    bb: Bounding Box модели без фейков [[minX, minY, minZ], [maxX, maxY, maxZ], [spanX, spanY, spanZ]]
    bb_fake: Bounding Box модели с фейками
    model_path: путь к файлу модели
    model_name: имя файла модели
    """

    def __init__(self):
        self.model_path = ''
        self.cnt_vertexes = 0
        self.cnt_faces = 0
        self.objects = {}
        self.bb = [[None, None, None], [None, None, None], [None, None, None]]
        self.bb_fake = [[None, None, None], [None, None, None], [None, None, None]]
        self.mtllib = None
        self.materials = set()
        self.filestat = None

    def scan_file(self, filename):
        """Читает файл модели и собирает всю статистику"""
        # Сюда будет аккумулироваться BB объекта
        self.model_path = filename

        self.filestat = os.stat(filename)

        bb = [[None, None, None], [None, None, None], [None, None, None]]
        obj_f, obj_v = 0, 0
        with open(filename, encoding='latin-1') as fh:
            for line in fh:
                line = line.strip()
                if line.startswith('v '):
                    self.cnt_vertexes += 1
                    obj_v += 1
                    coords = [float(_) for _ in line[2:].split()]
                    for i in range(3):
                        if bb[0][i] is None or coords[i] < bb[0][i]:
                            bb[0][i] = coords[i]
                        if bb[1][i] is None or coords[i] > bb[1][i]:
                            bb[1][i] = coords[i]
                elif line.startswith('f '):
                    self.cnt_faces += 1
                elif line.startswith('o '):
                    object_name = line[2:].strip()
                    bb[2] = [bb[1][_] - bb[0][_] for _ in range(3)]
                    self.objects[object_name] = {
                        'cnt_vertexes': obj_v,
                        'bb': bb
                    }
                    obj_v = 0
                    bb = [[None, None, None], [None, None, None], [None, None, None]]
                elif line.startswith('mtllib '):
                    self.mtllib = line[7:].strip()
                elif line.startswith('usemtl '):
                    self.materials.add(line[7:].strip())

        # Если в модели не оказалось ни одного объекта, то засовываем всё в один объект:
        if not self.objects:
            bb[2] = [bb[1][_] - bb[0][_] for _ in range(3)]
            self.objects['*'] = {
                'cnt_vertexes': obj_v,
                'bb': bb
            }

        # Вычисляем BB модели: с фейками и без
        for obj_name, obj in self.objects.items():
            self._update_bb(self.bb_fake, obj['bb'])
            if not obj_name.endswith('_fake'):
                self._update_bb(self.bb, obj['bb'])

        self.bb[2] = [self.bb[1][_] - self.bb[0][_] for _ in range(3)]
        self.bb_fake[2] = [self.bb_fake[1][_] - self.bb_fake[0][_] for _ in range(3)]

    @staticmethod
    def _update_bb(tgt, src):
        """Расширяет Bounding Box tgt коробкой src"""
        for i in range(3):
            if tgt[0][i] is None or src[0][i] < tgt[0][i]:
                tgt[0][i] = src[0][i]
            if tgt[1][i] is None or src[1][i] > tgt[1][i]:
                tgt[1][i] = src[1][i]

    @property
    def area(self):
        """Возвращает площадь модели по XY, без фейков"""
        return self.bb[2][0] * self.bb[2][1]

    @property
    def volume(self):
        """Возвращает объём BB модели, без фейков"""
        return self.bb[2][0] * self.bb[2][1] * self.bb[2][2]

    @property
    def area_fake(self):
        """Возвращает площадь модели по XY, без фейков"""
        return self.bb_fake[2][0] * self.bb_fake[2][1]

    @property
    def volume_fake(self):
        """Возвращает объём BB модели, без фейков"""
        return self.bb_fake[2][0] * self.bb_fake[2][1] * self.bb_fake[2][2]

    def digest(self):
        """Печатает инфу по модели."""
        print('Model {}: {:.2f} MB V={s.cnt_vertexes} F={s.cnt_faces}'.format(os.path.basename(self.model_path),
                                                                              self.filestat.st_size / 1024 / 1024,
                                                                              s=self))
        print('BB: {:.3f} x {:.3f} x {:.3f} Sxy={:.3f}, V={:.3f}'.format(
            self.bb[2][0], self.bb[2][1], self.bb[2][2], self.area, self.volume
        ))
        print('Fake BB: {:.3f} x {:.3f} x {:.3f} Sxy={:.3f}, V={:.3f}'.format(
            self.bb_fake[2][0], self.bb_fake[2][1], self.bb_fake[2][2], self.area_fake, self.volume_fake
        ))
        print('MTL: {s.mtllib}, materials: {s.materials}'.format(s=self))
        print('{} objects:'.format(len(self.objects)))
        for obj_name, info in self.objects.items():
            obj_name = obj_name.rjust(32)
            if obj_name.endswith('_fake'):
                obj_name = colors.blue(obj_name)
            print('{} F={:<5d} BB={:6.3f} x {:6.3f} x {:6.3f} Sxy={:7.3f}'.format(
                obj_name, info['cnt_vertexes'],
                info['bb'][2][0], info['bb'][2][1], info['bb'][2][2],
                info['bb'][2][0] * info['bb'][2][1]
            ))


def get_flow_file(payload, key):
    """Ожидает увидеть в payload[key] пару TOKEN/FILENAME, проверяет существование файла и возвращает путь к нему.
    На всякую лажу делает abort(400). """
    try:
        token, filename = payload[key].split('/')
    except (ValueError, KeyError) as e:
        abort(400, gettext('Malformed %(key)s value.', key=key))

    src = os.path.join(app.config['FLOW_UPLOAD_TMP_DIR'], token, filename)
    if not os.path.exists(src):
        abort(400, gettext('Source file %(token)s/%(filename)s not found for %(key)s.', token=token, filename=filename,
                           key=key))

    return src, token, filename


def find_upload_server(host):
    for server in current_app.config['UPLOAD_SERVERS']:
        if host == server['host']:
            return server
    return None


def get_upload_slot_dir(value):
    """Возвращает путь к директории Upload Slot'а, отсылка на которую в терминах синтаксиса API ("upload-slot@hostname/SLOT)
    лежит в `value`. Проверяет валиндость входной строки и существование директории, выбрасывает abort()"""
    try:
        host, slot = value[12:].split('/')
    except ValueError:
        abort(400, gettext('Malformed %(key)s value.', key='assets'))

    server = find_upload_server(host)
    if not server:
        abort(400, gettext('Server %(server)s not found.', server=host))

    path = os.path.join(server['local_basedir'], slot)
    if not os.path.isdir(path):
        abort(400, gettext('Upload slot %(slot)s not found.', slot=slot))

    return server, slot, path


def coerce_str_i18n(data, nullable=True):
    """Приводит переменную data к str_i18n, в случае ошибки выбрасывает ValueError"""
    if data is None and nullable:
        return None
    if type(data) is dict:
        for k, v in data.items():
            if type(k) is not str or type(v) is not str:
                raise TypeError
        return data
    if type(data) is str:
        return data
    raise ValueError


def coerce_quaternion(data, nullable=True):
    """Приводит переменную data к quaternion, в случае ошибки выбрасывает ValueError"""
    if data is None and nullable:
        return None
    try:
        q = [float(data[i]) for i in range(4)]
        return q
    except (ValueError, KeyError, TypeError, IndexError):
        raise ValueError


def unzip_footage_tour(archive, footage, tour):
    """Распаковывает архив archive в footage и tour. Возвращает список предупреждений,
    ошибки выбрасывает эксепшенами. У footage и tour должны быть созданны ассеты files."""

    def extract_meta(fh, filename, model):
        """Распаковывает мету в модель model из файла filename архива fh."""
        meta = fh.read(filename).decode()
        try:
            setattr(model, 'meta', json.loads(meta))
        except json.decoder.JSONDecodeError as e:
            raise Exception('Ошибка в JSON-файле {}: {}'.format(filename, str(e)))

    warnings = []
    with zipfile.ZipFile(archive, 'r') as fh:
        files = fh.namelist()

        if 'tour/_meta.json' not in files:
            warnings.append('В архиве нет метаданных для тура.')
        if 'footage/_meta.json' not in files:
            warnings.append('В архиве нет метаданных для съёмки.')

        for file in files:
            # Некоторые архиваторы лупят отдельную запись для директорий, пропускаем их
            if file.endswith('/'):
                continue
            if file == 'tour/_meta.json':
                extract_meta(fh, file, tour)
            elif file == 'footage/_meta.json':
                extract_meta(fh, file, footage)
            elif file.startswith('tour/'):
                dst = tour.in_files(file[5:])
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(tour.in_files(file[5:]), 'wb') as out:
                    out.write(fh.read(file))
            elif file.startswith('footage/'):
                dst = footage.in_files(file[8:])
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(footage.in_files(file[8:]), 'wb') as out:
                    out.write(fh.read(file))
            else:
                warnings.append('Странный файл в архиве {}. Непонятно, к чему он.'.format(file))

        return warnings


class ValidateOnSetMixin:
    def __setattr__(self, name: str, value: typing.Any) -> None:
        """Call the validator when we set the field (by default it only runs on __init__)"""
        for attribute in [a for a in getattr(self.__class__, '__attrs_attrs__', []) if a.name == name]:
            if attribute.type is not None:
                if isinstance(value, attribute.type) is False:
                    raise TypeError('{}.{} cannot set {} because it is not a {}'.format(
                        self.__class__.__name__, attribute.name, value, attribute.type.__name__))
            if attribute.validator is not None:
                attribute.validator(self, attribute, value)
        super().__setattr__(name, value)


def get_content(dir_name, rel_path):
    """Формирует словарь со списком вложенных папок и файлов """
    content = {}
    folders = []
    files = []
    abs_path = os.path.join(dir_name, rel_path)
    content_directory = os.listdir(abs_path)

    for file in content_directory:
        abs_path_file = os.path.join(abs_path, file)
        if os.path.isdir(abs_path_file):
            folders.append(file)
        else:
            files.append(
                {'name': file, 'created': datetime.datetime.fromtimestamp(os.path.getctime(abs_path_file)),
                 'size': f'{(os.path.getsize(abs_path_file)) / 1024:.2f} Кб'})

    content['folders'] = sorted(folders, key=lambda k: k.lower())
    content['files'] = sorted(files, key=lambda k: k['name'])
    return content


def process_frames(tour, progress):
    log_builder = logging.getLogger('builder')
    footage = tour.footage
    meta = footage.meta

    # Общее количество фреймов
    cnt_frames = 0
    cur_frame = 0
    for set_ in meta['sets'].values():
        cnt_frames += len(set_['frames'])

    progress.action('Создаются фреймы', cnt_frames)

    for set_ in meta['sets'].values():
        for res in meta['resolutions']:
            os.makedirs(tour.footage.in_files('frames', str(set_['id']), 'x'.join([str(_) for _ in res])),
                        exist_ok=True)

        for frame_id, frame in set_['frames'].items():
            cur_frame += 1
            progress.say(f"Создаётся фрейм {frame_id} в сете {set_['id']}")

            for res in meta['resolutions']:
                downsize_img(
                    footage.in_files('frames', str(set_['id']), frame['filename']),
                    footage.in_files('frames', str(set_['id']), 'x'.join([str(_) for _ in res]),
                                     '{}.jpg'.format(frame_id)),
                    res,
                    'crop'
                )
    progress.end()
