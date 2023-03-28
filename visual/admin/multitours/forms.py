from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, IntegerField, HiddenField, RadioField, validators as v
from visual.util import FiltersForm, SwitchWidget


class MultitourFilter(FiltersForm):
    __remember_fields__ = ['sort']

    sort = SelectField('Сортировка', choices=[('created', 'По времени создания'), ('title', 'По названию')], default='created')
    search = StringField('Поиск по названию')

class MultitoursMovedFilter(FiltersForm):
    search_by = SelectField('Искать по', default='', choices=[
        ('', 'Искать по'),
        ('local_id', 'По id мультитура'),
        ('remote_id', 'По новому id мультитура'),
        ('created', 'По дате переноса'),
        ('server', 'Куда'),
    ])
    search_field = StringField('Поиск ', )
