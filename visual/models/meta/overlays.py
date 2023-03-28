from flask_babel import gettext
from flask import abort

from visual.util import coerce_str_i18n


class Overlay:
    def __init__(self, meta, id, data=None):
        self.meta = meta
        self.id = id
        if data is None:
            data = {}

        self.name = data.get('name')
        self.type = data.get('type')
        self.widget = data.get('widget')
        self.tooltip = data.get('tooltip')
        self.actions = data.get('actions')
        self.class_ = data.get('class')
        self.skybox_overrides = data.get('skybox_overrides')
        self.show_in_dollhouse = data.get('show_in_dollhouse')


    def api_repr(self):
        """Отдаёт объект в виде словаря для ответа API."""
        r = {prop: getattr(self, prop) for prop in
             ('name', 'type', 'widget', 'tooltip', 'actions', 'skybox_overrides', 'show_in_dollhouse') if getattr(self, prop, None) is not None}
        if self.class_:
            r['class'] = self.class_
        return r

    def __repr__(self):
        return '<Overlay #{o.id} type={o.type}>'.format(o=self)

    @classmethod
    def from_meta(cls, meta, id, data):
        o = cls(meta=meta, id=id, data=data)
        return o

    def update_from_api_request(self, payload):
        warnings = []
        simple_props = {'name': str, 'type': str, 'widget': dict, 'tooltip': coerce_str_i18n, 'actions': dict,
                        'skybox_overrides': dict, 'show_in_dollhouse': bool}
        skip_props = {}

        if 'type' not in payload:
            abort(400, gettext('Not enough %(object)s properties %(prop)s.', object='overlay', prop='type'))

        if 'widget' not in payload:
            abort(400, gettext('Not enough %(object)s properties %(prop)s.', object='overlay', prop='widget'))

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
