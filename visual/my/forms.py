from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FileField, FloatField
from wtforms import validators as v
from flask_babel import lazy_gettext


def strip(t):
    if isinstance(t, str):
        return t.strip()
    return t


class EstateForm(FlaskForm):
    title = StringField('Название', validators=[v.data_required(lazy_gettext("Enter folder name"))], filters=[strip])
    address = TextAreaField('Адрес', filters=[strip])
    lat = FloatField('Широта', validators=[v.optional()])
    lon = FloatField('Долгота', validators=[v.optional()])
    preview = FileField('Картинка')

