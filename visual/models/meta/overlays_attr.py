"""Неподключенный и недописанный модуль поддержки оверлеев на attr. Довести до ума и распространить на все классы меты.
"""

import attr
from attr import validators as v
from flask import abort
from flask_babel import gettext

from visual.util import ValidateOnSetMixin


def validator_quaternion(instance, attrib, value):
    if type(value) is not list or len(value) != 4:
        raise ValueError('Bad quaternion ({})'.format(attrib.name))


def validator_vector3(instance, attrib, value):
    if type(value) is not list or len(value) != 3:
        raise ValueError('Bad vector3 ({})'.format(attrib.name))


def validator_rgba(instance, attrib, value):
    if type(value) is not list or len(value) != 3:
        raise ValueError('Bad rgba ({})'.format(attrib.name))


class MetaEntity(ValidateOnSetMixin):
    """Базовый класс для классов меты"""
    def update_from_api_request(self, payload):
        warnings = []
        for key, value in payload.items():
            attrib = attr.fields_dict(self.__class__).get(key)
            if attrib:
                if value is None:
                    setattr(self, key, attrib.default)
                else:
                    try:
                        setattr(self, key, value)
                    except TypeError:
                        abort(400, gettext('Bad data type for property %(property)s', property=key))
            else:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

    def api_repr(self):
        r = {}
        for attribute in [a for a in getattr(self.__class__, '__attrs_attrs__', [])]:
            if getattr(self, attribute.name) != attribute.default:
                r[attribute.name] = getattr(self, attribute.name)

        return r


@attr.s
class Overlay(ValidateOnSetMixin):
    id = attr.ib()
    meta = attr.ib()    # TourMeta
    type = attr.ib(default=None, validator=v.optional(v.instance_of(str)))
    widget = attr.ib(default=None, repr=False)
    tooltip = attr.ib(default='', validator=v.instance_of(str))
    actions = attr.ib(default=attr.Factory(dict), validator=v.instance_of(dict), repr=False)
    class_ = attr.ib(default=attr.Factory(list), validator=v.instance_of(list), repr=False)

    def create_widget(self, data):
        """Создаёт self.widget нужного класса исходя из self.type"""
        if self.type == 'poliyline':
            self.widget = OverlayPolylineWidget.from_meta(data)
        elif self.type == 'polygon':
            self.widget = OverlayPolygonWidget.from_meta(data)
        elif self.type == 'ellipse':
            self.widget = OverlayEllipseWidget.from_meta(data)
        elif self.type == 'image':
            self.widget = OverlayImageWidget.from_meta(data)
        elif self.type == 'text':
            self.widget = OverlayTextWidget.from_meta(data)
        else:
            raise ValueError(gettext('Bad overlay type %(type)s', type=self.type))

    @classmethod
    def from_meta(cls, meta, id_, data):
        o = cls(
            id=id_,
            meta=meta,
            type=data['type'],
            widget=None
        )
        for oparam in ('tooltip', 'actions'):
            if oparam in data:
                setattr(o, oparam, data[oparam])
        if 'class' in data:
            o.class_ = data['class']
        o.create_widget(data['widget'])
        return o

    def update_from_api_request(self, payload):
        simple_props = ('tooltip', 'actions', 'class')
        skip_props = ()
        warnings = []
        for key, value in payload.items():
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, value)
                    except TypeError:
                        abort(400, gettext('Bad data type for property %(property)s', property=key))
            elif key == 'type':
                if 'widget' not in payload:
                    abort(400, gettext('You can not set overlay type without sending new widget data.'))
                if self.type != value:
                    # Если тип изменился, то пересоздаём виджет
                    self.type = value
                    self.create_widget(payload['widget'])
            elif key == 'widget':
                if self.widget is None:
                    if 'type' not in payload:
                        abort(400, gettext('Please specify overlay type.'))
                    self.type = payload['type']
                    self.create_widget(payload['widget'])
                else:
                    self.widget.update_from_api_request(payload['widget'])
            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

    def api_repr(self):
        """Отдаёт объект в виде словаря для ответа API."""
        attrs = attr.fields_dict(self.__class__)
        r = {prop: getattr(self, prop) for prop in ('type', 'tooltip', 'actions') if getattr(self, prop, None) != attrs[prop].default}

        if self.class_ != attrs['class_'].default:
            r['class'] = self.class_

        if self.widget:
            r['widget'] = self.widget.api_repr()

        return r


@attr.s
class OverlayPolylineWidget(MetaEntity):
    pos = attr.ib()
    coords = attr.ib()
    q = attr.ib(default=[0, 0, 0, 1])
    color = attr.ib(default=[0, 255, 0, 1])
    width = attr.ib(default=None)
    text = attr.ib(default=None)
    arrows = attr.ib(default=None)

    @classmethod
    def from_meta(cls, data):
        o = cls(
            pos=data['pos'],
            coords=data['coords']
        )
        for oparam in ('q', 'color', 'width', 'text', 'arrows'):
            if oparam in data:
                setattr(o, oparam, data[oparam])

        return o


@attr.s
class OverlayPolygonWidget(MetaEntity):
    pos = attr.ib()
    coords = attr.ib()
    faces = attr.ib(default=None)
    q = attr.ib(default=[0, 0, 0, 1])
    fill = attr.ib(default=[0, 255, 0, 0.7])
    fill_hover = attr.ib(default=None)
    border = attr.ib(default=None)

    @classmethod
    def from_meta(cls, data):
        o = cls(
            pos=data['pos'],
            coords=data['coords']
        )
        for oparam in ('faces', 'q', 'fill', 'fill_hover', 'border'):
            if oparam in data:
                setattr(o, oparam, data[oparam])

        return o


@attr.s
class OverlayEllipseWidget(MetaEntity):
    pos = attr.ib()
    radiuses = attr.ib()
    q = attr.ib(default=[0, 0, 0, 1])
    fill = attr.ib(default=[0, 255, 0, 0.7])
    fill_hover = attr.ib(default=None)
    border = attr.ib(default=None)

    @classmethod
    def from_meta(cls, data):
        o = cls(
            pos=data['pos'],
            radiuses=data['radiuses'],
        )
        for oparam in ('q', 'fill', 'fill_hover', 'border'):
            if oparam in data:
                setattr(o, oparam, data[oparam])

        return o


@attr.s
class OverlayImageWidget(MetaEntity):
    pos = attr.ib()
    q = attr.ib(default=[0, 0, 0, 1])
    billboardmode = attr.ib(default=False)
    perspective = attr.ib(default=True)
    url = attr.ib(default=None)         # либо url, либо preset
    preset = attr.ib(default=None)
    size = attr.ib(default=None)

    @classmethod
    def from_meta(cls, data):
        o = cls(
            pos=data['pos']
        )
        for oparam in ('q', 'billboardmode', 'perspective', 'url', 'preset', 'size'):
            if oparam in data:
                setattr(o, oparam, data[oparam])

        return o


@attr.s
class OverlayFont(MetaEntity):
    pass


@attr.s
class OverlayBar(MetaEntity):
    pass


@attr.s
class OverlayLeg(MetaEntity):
    pass


@attr.s
class OverlayTextWidget(MetaEntity):
    pos = attr.ib()
    q = attr.ib(default=[0, 0, 0, 1])
    text = attr.ib(default='')
    billboardmode = attr.ib(default=False)
    perspective = attr.ib(default=True)
    font = attr.ib(factory=OverlayFont)
    bar = attr.ib(factory=OverlayBar)
    leg = attr.ib(factory=OverlayLeg)
