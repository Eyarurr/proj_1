from flask_babel import gettext
from flask import abort

from visual.util import coerce_str_i18n


class ActiveMesh:
    def __init__(self, meta, id, data=None):
        self.meta = meta
        self.id = id
        if data is None:
            data = {}

        self.name = data.get('name')
        self.type = data.get('type')
        self.title = data.get('title')
        self.hover = data.get('hover')
        self.look = data.get('look')
        self.active_when = data.get('active_when')
        self.actions = data.get('actions')
        self.class_ = data.get('class')

    def api_repr(self):
        """Отдаёт объект в виде словаря для ответа API."""
        resp = {prop: getattr(self, prop) for prop in ('name', 'title', 'type', 'hover', 'active_when', 'look', 'actions',
                                                       'title') if getattr(self, prop, None) is not None}
        if self.class_:
            resp['class'] = self.class_
        return resp

    def __repr__(self):
        return '<ActiveMesh #{o.id} type={o.type}>'.format(o=self)

    @classmethod
    def from_meta(cls, meta, id, data):
        o = cls(meta=meta, id=id, data=data)
        return o

    def update_from_api_request(self, payload):
        warnings = []
        simple_props = {'name': str, 'type': str, 'hover': dict, 'active_when': dict, 'title': coerce_str_i18n, 'actions': dict,
                        'look': dict, 'class': str}
        skip_props = {}

        if 'type' not in payload:
            abort(400, gettext('Not enough %(object)s properties %(prop)s.', object='active_mesh', prop='type'))

        for key, value in payload.items():
            if key in simple_props:
                if value is None:
                    setattr(self, key, None)
                else:
                    try:
                        setattr(self, key, simple_props[key](value))
                    except TypeError:
                        abort(400, gettext('Bad data type for property %(property)s', property=key))

            elif key not in skip_props:
                warnings.append(gettext('Unknown input property %(property)s', property=key))

        return warnings
