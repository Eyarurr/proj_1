from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, SelectField, FileField, IntegerField, RadioField, TextAreaField,\
    validators as v

from visual.models import Footage
from visual.util import FiltersForm, SwitchWidget


class FootageFilter(FiltersForm):
    __remember_fields__ = ['type', 'status']

    type = SelectField('Тип', choices=[('', 'Любые')] + list(Footage.TYPES.items()), default='')
    status = SelectField('Статус', choices=[('', 'Любой')] + list(Footage.STATUSES.items()), default='')
    search = StringField('Поиск по названию')


class FootageEditForm(FlaskForm):
    type = SelectField('Тип', choices=list(Footage.TYPES.items()))
    status = SelectField('Статус', choices=list(Footage.STATUSES.items()))
    meta_str = TextAreaField('Метаданные')


class FloorForm(FlaskForm):
    id = IntegerField('ID', validators=[v.data_required()])
    title = StringField('Подпись', validators=[v.optional()])
    big = FileField('Большая картинка')
    big_w = IntegerField(default=300, validators=[v.optional()])
    big_h = IntegerField(default=300, validators=[v.optional()])
    small = FileField('Маленькая картинка')
    small_source = RadioField('Откуда взять маленькую',
                              choices=[('upload', 'Загрузить'), ('resize', 'Сделать из большой')], default='resize')
    small_w = IntegerField(default=150, validators=[v.optional()])
    small_h = IntegerField(default=150, validators=[v.optional()])


class SkyboxForm(FlaskForm):
    id = IntegerField('ID', validators=[v.optional()])
    panorama = FileField(validators=[v.optional()])
    panorama_binocular = FileField(validators=[v.optional()])
    pos = StringField(validators=[v.data_required()])
    q = StringField(validators=[v.data_required()])
    floor = SelectField()
    title = StringField()
    is_start = BooleanField()
    start_q = StringField('Кватернион камеры на старте')
    render_type = RadioField('Тип рендера', choices=[('vray', 'Vray'), ('corona', 'Corona')], default='vray')
