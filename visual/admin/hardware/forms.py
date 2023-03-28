from flask_wtf import FlaskForm
from wtforms import FileField, StringField, SelectField, TextAreaField, IntegerField, DateField
from wtforms import validators as v

from visual.util import SwitchWidget, FiltersForm


class AddHardwareForm(FlaskForm):
    user_id = SelectField('Юзер', coerce=int, default=None)
    sn = StringField('Серийник')
    title = StringField('Наименование', validators=[v.data_required()])
    description = TextAreaField('Описание')
    img = FileField('Фото железки')
    price = IntegerField('Стоимость', validators=[v.optional()])
    buy_date = DateField('Дата приобретения', format='%Y-%m-%d', validators=[v.optional()], default=None)
    type = SelectField('Тип гаджета', )
    location = SelectField('Статус железяки', )
    display = SelectField('Показывать', choices=[('thumbnails', 'Плитка'), ('table', 'Таблица')],
                          default='table')

    def as_dict(self):
        result = {
            'user_id': self.user_id.data,
            'sn': self.sn.data,
            'title': self.title.data,
            'price': self.price.data,
            'buy_date': self.buy_date.data,
            'location': self.location.data,
        }
        return result


class SortHardwareForm(FiltersForm):
    __remember_fields__ = ['sorted_', ]

    user_id = SelectField('Юзер', coerce=int, default=None)
    sorted_ = SelectField('Сортировка', choices=[('', ''),
                                                 ('title', 'наименованию'),
                                                 ('key_date', 'дате последнего события'),
                                                 ('buy_date', 'дате приобретения'),
                                                 ('type_hw', 'типу железки'),
                                                 ],
                          default='')
    search_ = StringField('Поиск', default='')
