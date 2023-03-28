from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField
from wtforms import validators as v


class VacancyForm(FlaskForm):
    title = StringField('Название', validators=[v.data_required('У вакансии должно быть название.')])
    about = TextAreaField('Краткое описание', validators=[v.optional()])
    text = TextAreaField('Описание', validators=[v.data_required('У вакансии должно быть описание.')])
    salary = StringField('Зарплатная вилка', validators=[v.optional()])
    hidden = BooleanField('Скрыто')


