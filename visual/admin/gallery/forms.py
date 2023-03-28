from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, IntegerField, HiddenField, RadioField, validators as v
from visual.util import FiltersForm, SwitchWidget


class GalleryFilter(FiltersForm):
    __remember_fields__ = ['display']

    mode = HiddenField(default='-')
    search = StringField('Поиск по названию')
    tag = StringField('Тэг')
    sort = SelectField('Сортировка', choices=[('sort', 'Как решил модератор'), ('created', 'По времени создания'), ('title', 'По названию объекта и тура')], default='created')
    display = SelectField('Показывать', choices=[('thumbnails', 'Плитка'), ('table', 'Таблица')],
                          default='', widget=SwitchWidget())

