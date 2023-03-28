from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, DateTimeField, ValidationError, BooleanField, SelectField, FileField, HiddenField, FieldList
from wtforms.fields import EmailField
from wtforms import validators as v

from visual.util import PhoneField, MultiCheckboxField, FiltersForm
from visual.models import User


def strip(t):
    if isinstance(t, str):
        return t.strip()
    return t


class EditUserForm(FlaskForm):
    name = StringField('Имя', validators=[v.data_required('Задайте, пожалуйста, имя')], filters=[strip])
    email = EmailField('E-mail', validators=[v.data_required('Обязательно нужно ввести e-mail')], filters=[strip])
    email_confirmed = BooleanField('E-mail подтверждён')
    password = StringField('Пароль', filters=[strip])
    banned = BooleanField('Забанен')
    admin_comment = TextAreaField('Примечание', filters=[strip])
    stripe_customer_id = StringField('customer_id', validators=[v.optional()])
    contacts = HiddenField()
    avatar_ = FileField()
    avatar_delete = BooleanField()


class NewUserForm(EditUserForm):
    password = StringField('Пароль', validators=[v.data_required('Обязательно нужно указать пароль.')], filters=[strip])


class AddProductForm(FlaskForm):
    product_id = SelectField()


class EditProductForm(FlaskForm):
    plan_id = SelectField()
    last_payment_time = DateTimeField(validators=[v.Optional()])
    next_payment_time = DateTimeField(validators=[v.Optional()])
    meta_str = TextAreaField(validators=[v.InputRequired()])


class TagEditForm(FlaskForm):
    name = StringField(validators=[v.InputRequired()])
    label = StringField()
    prefix = StringField()
    suffix = StringField()
    crm_key = StringField()
    display_dict_keys = FieldList(StringField())
    display_dict_values = FieldList(StringField())
    # display_dict = StringField()
    

class UserFiltersForm(FiltersForm):
    """Фильтр списка пользователей"""

    __remember_fields__ = ['sort']

    search = StringField('Поиск по имени или e-mail', validators=[v.optional()], default='')
    paid = BooleanField('Только платные', validators=[v.optional()], default='')
    sort = SelectField(
        'Сортировка',
        choices=[
            ('created', 'По дате создания'),
            ('name', 'По имени'),
            ('cnt_tours', 'По количеству туров'),
            ('last_active', 'По времени последнего визита'),
        ],
        default='created'
    )
