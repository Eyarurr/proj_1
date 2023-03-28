import os
import re
import pytz
from datetime import datetime, timedelta
from collections import OrderedDict
import urllib.parse
import calendar

from flask import get_flashed_messages, Markup, json, current_app, g, request
from flask_babel import gettext, pgettext
from jinja_bs_modal import JinjaBSModalExtension
from flask_login import current_user

from visual import util
from visual.models import Offer, Footage, Vacancy
from visual.core import db, products

_FILESIZE_CACHE = {}


def register_jinja_filters(app):
    @app.context_processor
    def context_processors():
        """
        Возвращает flash-сообщения в виде [('error', [msg1, msg2, msg3]), ('success', [msg1, msg2]), ...]
        :return:
        """

        def make_flashes():
            result = {}
            for cat, msg in get_flashed_messages(with_categories=True):
                result.setdefault(cat, []).append(msg)
            return result

        def if_value(value, prefix='', suffix=''):
            if value:
                return Markup(prefix + str(value) + suffix)
            else:
                return ''

        def vacancies_exist():
            return db.session.query(Vacancy.id).filter_by(lang=g.get('lang', 'en'), hidden=False).first() is not None

        def footage_status_icon(footage):
            icons = {
                'loading': 'fa-upload',
                'queued': 'fa-water',
                'processing': 'fa-heartbeat',
                'testing': 'fa-wrench',
                'published': 'fa-check',
                'banned': 'fa-lock',
            }

            titles = {
                'loading': 'Загрузка исходников',
                'queued': 'В очереди на сборку',
                'processing': 'Идёт сборка',
                'testing': 'Тестируется',
                'published': 'Опубликовано',
                'banned': 'Заблокировано',
            }

            span = {
                'class': 'badge footage-status footage-status-{}'.format(footage.status)
            }
            if footage.status == 'queued' and footage.meta.get('_queued'):
                queued = footage.meta['_queued']
                if 'since' in queued:
                    try:
                        since = datetime.strptime(queued.get('since'), '%Y-%m-%dT%H:%M:%S.%f')
                        span['title'] = 'В очереди на сборку с {}'.format(
                            since.strftime('%d.%m %H:%M:%S'),
                        )
                    except ValueError:
                        span['title'] = 'Тур в очереди на сборку со странного времени {}, job {}'.format(
                            queued.get('since', '???'),
                            queued.get('job_id')
                        )

            elif footage.status == 'processing' and footage.meta.get('_processing'):
                processing = footage.meta['_processing']
                try:
                    since = datetime.strptime(processing.get('since'), '%Y-%m-%dT%H:%M:%S.%f')
                    dur = datetime.now() - since
                    span['title'] = 'Тур обрабатывается {dur}'.format(
                        dur=dur - timedelta(microseconds=dur.microseconds),
                    )
                except ValueError:
                    span['title'] = 'Тур обрабатывается со странного времени {}, job {}'.format(
                        processing.get('since', '???'),
                        processing.get('job_id')
                    )
            else:
                span['title'] = titles.get(footage.status, '???')

            span_html = '<span'
            for k, v in span.items():
                span_html += ' {}="{}"'.format(k, v)
            span_html += '>'

            return Markup(
                '{}<i class="fas {}"></i></span>'.format(
                    span_html,
                    icons.get(footage.status, '')
                )
            )

        def static_filesize(path):
            """
            Возвращает размер файла path, кешируя его (кеш хранится до перезагрузки модуля). Если файл не найден, возвращает False.
            :param path: Путь к файлу относительно
            :return:
            """
            abspath = os.path.join(current_app.root_path, path.strip('/'))
            if abspath not in _FILESIZE_CACHE:
                if os.path.isfile(abspath):
                    _FILESIZE_CACHE[abspath] = os.stat(abspath).st_size
                else:
                    _FILESIZE_CACHE[abspath] = False
            return _FILESIZE_CACHE[abspath]

        def current_datetime():
            """Возвращает datetime.datetime.now()"""
            return datetime.now()

        def proxy_pgettext(*args, **kwargs):
            return pgettext(*args, **kwargs)

        def date_sub(a, b):
            """
            Возвращает строку с человекочитаемой разницей дат a - b:
            2 года 5 месяцев 16 дней
            Если a is None, то оно равно текущей дате
            Если b is None, то возвращается строка '?'
            """
            if a is None:
                a = datetime.datetime.now()
            if b is None:
                return '?'
            d, m, y = 0, 0, 0
            d = a.day - b.day
            if d < 0:
                d = calendar.monthrange(b.year, b.month)[1] + d
                m -= 1
            m += a.month - b.month
            if m < 0:
                m = 12 + m
                y -= 1
            y += a.year - b.year

            res = []
            if y:
                res.append(f'{y} г')
            if m:
                res.append(f'{m} мес')
            if d:
                res.append(f'{d} дн')

            return ' '.join(res)

        return {
            'flashes': make_flashes,
            'if_value': if_value,
            'vacancies_exist': vacancies_exist,
            'footage_status_icon': footage_status_icon,
            'static_filesize': static_filesize,
            'current_datetime': current_datetime,
            'pgettext': proxy_pgettext,
            'date_sub': date_sub,
            'products': products
        }

    @app.template_filter('plural')
    def jinja_plural(x, var1, var2, var5):
        return util.plural(x, var1, var2, var5)

    @app.template_filter('timedelta_round')
    def timedelta_round(td):
        return td - timedelta(microseconds=td.microseconds)

    @app.template_filter('int2hms')
    def int2hms(sec):
        if sec is None:
            return ''
        return timedelta(seconds=sec)

    @app.template_filter('int2ms')
    def int2ms(sec):
        if sec is None:
            return ""
        return "%02d:%02d" % (sec / 60, sec % 60)

    @app.template_filter('float2msm')
    def float2msm(sec):
        if sec is None:
            return ""
        return "%02d:%06.3f" % (sec / 60, sec % 60)

    @app.template_filter('utcinlocal')
    def utcinlocal(utc_time, tz=None):
        if utc_time is not None:
            if tz is None and current_user.is_authenticated and current_user.timezone:
                tz = current_user.timezone
            else:
                tz = 'Etc/UTC'
            time_zone = pytz.timezone(tz)
            if utc_time.tzinfo:
                return utc_time.astimezone(time_zone)
            else:
                return time_zone.localize(utc_time)

    @app.template_filter('get_utc_delta')
    def get_utc_delta(etc ):
        TIMEZONES = current_app.config.get('TIMEZONES')
        if TIMEZONES.get(etc, None):
            math = re.findall('[-+]\d{2}', TIMEZONES.get(etc, None)[g.lang])
            return math[0]

    @app.template_filter('humantime')
    def humantime(ts, if_none='', not_today=False):
        if ts is None:
            return if_none
        if not_today == True:
            return ts.strftime('%d-%m-%Y %H:%M')
        now = pytz.utc.localize(datetime.now())
        if now.year == ts.year:
            if now.month == ts.month:
                if now.day == ts.day:
                    return gettext('today at ') + ts.strftime('%H:%M')
                elif 0 < (now - ts).days <= 1:
                    return gettext('yesterday at ') + ts.strftime('%H:%M')
            return ts.strftime('%d.%m %H:%M')
        return ts.strftime('%d.%m.%Y %H:%M')

    @app.template_filter('nl2br')
    def nl2br(t):
        if t is None:
            t = ''
        if isinstance(t, str):
            t = str(Markup.escape(t))
            t = t.strip().replace('\r', '').replace('\n', '<br>')
        return Markup(t)

    @app.template_filter('money')
    def jinja_money(x):
        if x is None:
            return '0'
        if type(x) is str:
            x = float(x)
        return '{:,}'.format(round(x)).replace(',', ' ')

    @app.template_filter('ellipsis')
    def ellipsis(x, length):
        return x[:length].rsplit(' ', 1)[0] + '...' if len(x) > length else x

    @app.template_filter('url_host')
    def url_host(url):
        parts = urllib.parse.urlsplit(url)
        if not parts.scheme:
            parts = urllib.parse.urlsplit('https://' + url)
        return parts.netloc

    @app.template_filter('url_host_tail')
    def url_host_tail(url):
        if not url:
            return None
        parts = urllib.parse.urlsplit(url)
        if not parts.scheme:
            parts = urllib.parse.urlsplit('https://' + url)
        return os.path.split(parts.path)[-1]

    @app.template_filter('offer_type_label')
    def offer_type_label(offer, extra=None):
        if extra == 'cnt':
            extra = ' ({})'.format(offer.cnt_tours)
        else:
            extra = ''

        return Markup(
            '<span class="badge offer-type-{}">{}{}</span>'.format(
                offer.type, Offer.TYPES.get(offer.type, offer.type), extra
            )
        )

    @app.template_filter('footage_type_label')
    def footage_type_label(footage):
        return Markup('<span class="badge tour-type-{}">{}</span>'.format(
            footage.type, Footage.TYPES.get(footage.type, footage.type)
        ))

    @app.template_filter('yesno')
    def yesno(x):
        return 'Да' if x else 'Нет'

    @app.template_filter('json_neat')
    def json_neat(data):
        return json.dumps(data, indent=4, ensure_ascii=False, sort_keys=True)

    @app.template_filter('to_json')
    def json_neat(data):
        return json.dumps(data)

    @app.template_filter('sec2datetime')
    def sec2datetime(ts):
        return datetime.fromtimestamp(ts)

    @app.template_filter('sec2deltatime')
    def sec2deltatime(ts):
        return timedelta(seconds=ts)

    @app.template_filter('absurl')
    def absurl(url):
        """Если url относительный, то превращает его в полный в домене biganto.com"""
        if not url.startswith('http://') and not url.startswith('https://'):
            if not url.startswith('/'):
                url = '/' + url
            return 'https://' + request.host + url
        return url

    app.jinja_env.add_extension(JinjaBSModalExtension)
