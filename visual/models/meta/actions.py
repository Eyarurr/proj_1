import os
import re
import shutil
import uuid

from flask_babel import gettext
from flask import abort, current_app

from visual.util import coerce_quaternion, coerce_str_i18n, get_flow_file, unlink_calm
from PIL import Image, UnidentifiedImageError


class ActionGoto:
    type = 'goto'

    def __init__(self, data=None):
        if data is None:
            data = {}

        self.name = data.get('name')
        self.skybox = data.get('skybox')
        self.skybox_offset = data.get('skybox_offset')
        self.q = data.get('q')
        self.duration = data.get('duration')

    def api_repr(self):
        r = {prop: getattr(self, prop) for prop in ('name', 'skybox', 'skybox_offset', 'q', 'duration') if getattr(self, prop, None) is not None}
        r['type'] = 'goto'
        return r

    def update_from_api_request(self, payload, meta=None):
        warnings = []
        simple_props = {'name': str, 'skybox': str, 'skybox_offset': int, 'q': coerce_quaternion, 'duration': int}
        skip_props = {'type'}

        if 'skybox' not in payload:
            abort(400, gettext('Target skybox must be specified for action "goto".'))

        for key, value in payload.items():
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, simple_props[key](value))
                    except (TypeError, ValueError):
                        abort(400, gettext('Bad data type for property %(property)s', property=key))

            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

        return warnings


class ActionPopup:
    type = 'popup'

    def __init__(self, data=None):
        if data is None:
            data = {}
        self.name = data.get('name')
        self.bg = data.get('bg')
        self.size = data.get('size')
        self.html = data.get('html')
        self.iframe = data.get('iframe')
        self.image = data.get('image')
        self.html_get = data.get('html_get')
        self.title = data.get('title')
        self.body = data.get('body')
        self.buttons = data.get('buttons')

    def api_repr(self):
        r = {prop: getattr(self, prop) for prop in ('name', 'bg', 'size', 'html', 'iframe', 'image', 'html_get',
                                                    'title', 'body', 'buttons') if getattr(self, prop, None) is not None}
        r['type'] = 'popup'
        return r

    def update_from_api_request(self, payload, meta=None):
        warnings = []
        simple_props = {
            'name': str,
            'bg': list,
            'size': list,
            'html': coerce_str_i18n,
            'iframe': str,
            'html_get': str,
            'title': coerce_str_i18n,
            'body': coerce_str_i18n,
            'buttons': list
        }
        skip_props = {'type'}
        required_props = ('html', 'iframe', 'html_get', 'title', 'body', 'buttons', 'image@flow', 'image')
        for k in required_props:
            if k in payload and payload[k] is None:
                if k == 'image@flow' or k == 'image':
                    if self.image:
                        unlink_calm(meta.tour.in_files(self.image))
                    setattr(self, 'image', None)
                else:
                    setattr(self, k, None)
                payload.pop(k, None)

        content_attrs_msg = gettext('Popup action should contain either `html`, either `iframe`, either `html_get`, '
                                    'either `title`+`body`+buttons`,  either `image@flow` attributes')
        match = set(payload) & set(required_props)
        if len(match) == 0 or len(match) > 1 and not match.issubset({'title', 'body', 'buttons'}):
            abort(400, content_attrs_msg)

        for key, value in payload.items():
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, simple_props[key](value))
                    except (TypeError, ValueError):
                        abort(400, gettext('Bad data type for property %(property)s', property=key))

            elif key == 'image@flow':
                src, _, filename = get_flow_file(payload, key)
                _, ext = os.path.splitext(src)
                if ext.lower() not in ('.jpg', '.jpeg', '.png'):
                    abort(404, gettext('Unsupported image extension %(extension)s in file %(filename)s. File skipped.',
                                       extension=ext, filename=filename))
                if os.path.getsize(src) / 1024 ** 2 > current_app.config.get('MAX_POPUP_IMAGE_SIZE'):
                    abort(404, gettext("File size should not exceed %(max_size)d MB", max_size=current_app.config.get('MAX_POPUP_IMAGE_SIZE')))
                try:
                    Image.open(src)
                except UnidentifiedImageError as e:
                    abort(404, gettext("Unknown image type in %(key)s.", key=filename))
                # обрабатываем приемник
                meta.tour.mkdir()
                os.makedirs(meta.tour.in_files('images'), exist_ok=True)
                if self.image:
                    unlink_calm(meta.tour.in_files(self.image))
                filename = str(uuid.uuid4().hex) + ext
                self.image = 'images/' + filename
                shutil.move(src, meta.tour.in_files('images', filename))
            elif key == 'image':
                try:
                    _, _ = payload[key].split('/')
                except (ValueError, KeyError) as e:
                    abort(400, gettext('Malformed %(key)s value.', key=key))

                if not os.path.exists(meta.tour.in_files(value)):
                    abort(404, gettext('File %(filename)s not found.', filename=value))
            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

        return warnings


class ActionSound:
    type = 'sound'

    def __init__(self, data):
        if data is None:
            data = {}

        self.name = data.get('name')
        self.url = data.get('url')

    def api_repr(self):
        r = {prop: getattr(self, prop) for prop in ('name', 'url') if getattr(self, prop, None) is not None}
        r['type'] = 'sound'
        return r

    def update_from_api_request(self, payload, meta=None):
        warnings = []
        simple_props = {'name': str, 'url': str}
        skip_props = {'type'}

        if 'url' not in payload:
            abort(400, gettext('URL must be specified for action "sound".'))

        for key, value in payload.items():
            # print(key)
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, simple_props[key](value))
                    except (TypeError, ValueError):
                        abort(400, gettext('Bad data type for property %(property)s', property=key))

            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

        return warnings


class ActionVideo:
    type = 'video'

    def __init__(self, data):
        if data is None:
            data = {}

        self.name = data.get('name')
        self.urls = data.get('urls')
        self.size = data.get('size')

    def api_repr(self):
        r = {prop: getattr(self, prop) for prop in ('name', 'urls', 'size') if getattr(self, prop, None) is not None}
        r['type'] = 'video'
        return r

    def update_from_api_request(self, payload, meta=None):
        warnings = []
        simple_props = {'name': str}
        skip_props = {'type'}

        if 'urls' not in payload:
            abort(400, gettext('Video URLs must be specified for action "video".'))

        for key, value in payload.items():
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, simple_props[key](value))
                    except (TypeError, ValueError):
                        abort(400, gettext('Bad data type for property %(property)s', property=key))
            elif key == 'urls':
                try:
                    self.urls = {str(k): str(v) for k, v in payload['urls'].items()}
                except (AttributeError, TypeError, ValueError):
                    abort(400, gettext('Invalid %(property)s value', property='urls'))
                if not self.urls:
                    abort(400, gettext('You must specify at least one URL for video action.'))
            elif key == 'size':
                size = [None, None]
                try:
                    for i in range(2):
                        size[i] = str(payload['size'][i])
                        if not re.match(r'\d+(%|px)', size[i]):
                            raise ValueError
                except (TypeError, ValueError, IndexError):
                    abort(400, gettext('Malformed %(key)s value.', key='size'))
                self.size = size
            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

        return warnings


class ActionHref:
    type = 'href'

    def __init__(self, data):
        if data is None:
            data = {}

        self.name = data.get('name')
        self.url = data.get('url')
        self.target = data.get('target')

    def api_repr(self):
        r = {prop: getattr(self, prop) for prop in ('name', 'url', 'target') if getattr(self, prop, None) is not None}
        r['type'] = 'href'
        return r

    def update_from_api_request(self, payload, meta=None):
        warnings = []
        simple_props = {'name': str, 'url': str}
        skip_props = {'type'}

        if 'url' not in payload:
            abort(400, gettext('URL must be specified for action "href".'))

        for key, value in payload.items():
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, simple_props[key](value))
                    except (TypeError, ValueError):
                        abort(400, gettext('Bad data type for property %(property)s', property=key))
            elif key == 'target':
                if value not in ('_self', '_blank', '_top', '_parent'):
                    abort(400, gettext('Malformed %(key)s value.', key='target'))
                self.target = value
            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

        return warnings


class ActionTour:
    type = 'tour'

    def __init__(self, data):
        if data is None:
            data = {}

        self.name = data.get('name')
        self.id = data.get('id')
        self.skybox = data.get('skybox')
        self.q = data.get('q')
        self.keep_position = data.get('keep_position')
        self.target = data.get('target')

    def api_repr(self):
        r = {prop: getattr(self, prop) for prop in ('name', 'id', 'skybox', 'q', 'keep_position', 'target') if getattr(self, prop, None) is not None}
        r['type'] = 'tour'
        return r

    def update_from_api_request(self, payload, meta=None):
        warnings = []
        simple_props = {'name': str, 'id': int, 'keep_position': bool, 'skybox': str, 'q': coerce_quaternion}
        skip_props = {'type'}

        if 'id' not in payload:
            abort(400, gettext('Tour ID must be specified for action "tour".'))

        for key, value in payload.items():
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, simple_props[key](value))
                    except (TypeError, ValueError):
                        abort(400, gettext('Bad data type for property %(property)s', property=key))
            elif key == 'target':
                if value not in ('_self', '_blank', '_top', '_parent'):
                    abort(400, gettext('Malformed %(key)s value.', key='target'))
                self.target = value
            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

        return warnings


class ActionOffer:
    """OBSOLETE"""
    type = 'offer'

    def __init__(self, data):
        if data is None:
            data = {}

        self.name = data.get('name')
        self.id = data.get('id')
        self.tour_id = data.get('tour_id')
        self.skybox = data.get('skybox')
        self.q = data.get('q')
        self.target = data.get('target')

    def api_repr(self):
        r = {prop: getattr(self, prop) for prop in ('name', 'id', 'tour_id', 'skybox', 'q', 'target') if getattr(self, prop, None) is not None}
        r['type'] = 'offer'
        return r

    def update_from_api_request(self, payload, meta=None):
        warnings = []
        simple_props = {'name': str, 'id': int, 'tour_id': int, 'skybox': str, 'q': coerce_quaternion}
        skip_props = {'type', 'target'}

        if 'id' not in payload:
            abort(400, gettext('Tour ID must be specified for action "offer".'))

        for key, value in payload.items():
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, simple_props[key](value))
                    except (TypeError, ValueError):
                        abort(400, gettext('Bad data type for property %(property)s', property=key))
            elif key == 'target':
                if value not in ('_self', '_blank', '_top', '_parent'):
                    abort(400, gettext('Malformed %(key)s value.', key='target'))
                self.target = value
            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

        return warnings


class ActionToggleClass:
    type = 'clickable_toggle_class'

    def __init__(self, data):
        if data is None:
            data = {}

        self.name = data.get('name')
        self.class_ = data.get('class')

    def api_repr(self):
        r = {'type': 'clickable_toggle_class'}
        if self.class_:
            r['class'] = self.class_
        if self.name:
            r['name'] = self.name
        return r

    def update_from_api_request(self, payload, meta=None):
        warnings = []
        simple_props = {'name': str, 'class': str}
        skip_props = {}

        for key, value in payload.items():
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, simple_props[key](value))
                    except (TypeError, ValueError):
                        abort(400, gettext('Bad data type for property %(property)s', property=key))
            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

        return warnings


class ActionSwitch:
    """EXPERIMENTAL"""
    type = 'switch'

    def __init__(self, data):
        if data is None:
            data = {}

        self.name = data.get('name')
        self.on = data.get('on')
        self.off = data.get('off')

    def api_repr(self):
        r = {prop: getattr(self, prop) for prop in ('name', 'on', 'off') if getattr(self, prop, None) is not None}
        r['type'] = 'switch'
        return r


class ActionShadow:
    type = 'shadow'

    def __init__(self, data):
        if data is None:
            data = {}

        self.selection = data.get('selection')
        self.name = data.get('name')
        self.mode = data.get('mode')
        self.cycle = data.get('cycle')

    def api_repr(self):
        r = {prop: getattr(self, prop) for prop in ('cycle', 'mode', 'selection', 'name') if getattr(self, prop, None) is not None}
        r['type'] = 'shadow'
        return r

    def update_from_api_request(self, payload, meta=None):
        warnings = []
        simple_props = {'selection': list, 'cycle': bool, 'mode': str, 'name': str}
        skip_props = {'type'}
        mode = ('next', 'prev', 'random')

        for key, value in payload.items():
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, simple_props[key](value))
                    except (TypeError, ValueError):
                        abort(400, gettext('Bad data type for  property %(property)s', property=key))
                if key == 'mode' and value not in mode:
                    abort(400, gettext('Bad data type for property %(property)s', property=key))
            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

        return warnings


class Action:
    TYPES = {
        'goto': ActionGoto,
        'popup': ActionPopup,
        'sound': ActionSound,
        'video': ActionVideo,
        'href': ActionHref,
        'tour': ActionTour,
        'offer': ActionOffer,
        'clickable_toggle_class': ActionToggleClass,
        'switch': ActionSwitch,
        'shadow': ActionShadow
    }

    @classmethod
    def create(cls, type_=None, data=None):
        if type_ is None:
            if 'type' not in data:
                raise ValueError('Action.type not specified.')
            type_ = data['type']
        if type_ not in cls.TYPES:
            raise ValueError('Unknown action Action.type "{}"'.format(type_))

        if data is None:
            data = {}

        o = cls.TYPES[type_](data)
        return o
