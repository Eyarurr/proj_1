from flask_wtf import FlaskForm
from wtforms import StringField, FileField, BooleanField
from wtforms import validators as v


class PartnerForm(FlaskForm):
    title = StringField('Партнёр', validators=[v.optional()])
    url = StringField('Ссылка', validators=[v.optional(), v.url()])
    logo = FileField('Логотип', validators=[v.data_required('У партнёра должен быть логотип')])
    hidden = BooleanField('Скрыто')


class PartnerWithLogoForm(PartnerForm):
    logo = FileField('Логотип', validators=[v.optional()])
