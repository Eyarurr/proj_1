from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, FileField, SelectField, RadioField, DateField, IntegerField
from wtforms import validators as v


class SomaForm(FlaskForm):
    a = StringField('Однажды')
    b = TextAreaField('В студёную')
    c = BooleanField('Зимнюю', validators=[v.optional()])
    d = FileField('Пору', validators=[v.data_required()])
    e = SelectField('Я из лесу', choices=[(1, 'Раз'), (2, 'Два')])
    f = RadioField('Вышел', choices=[(1, 'Раз'), (2, 'Два')])

