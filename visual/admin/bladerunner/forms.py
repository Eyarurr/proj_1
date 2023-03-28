
from flask_wtf import FlaskForm
from wtforms import validators as v, FileField
from visual.util import FiltersForm
from wtforms.fields import EmailField
from visual.models import BROrder, BROrderAsset

from wtforms import StringField, TextAreaField, SelectField, IntegerField, FloatField, DateField, HiddenField, \
    BooleanField

class BROrdersFiltersForm(FiltersForm):
    """Фильтр списка заказов"""

    date = DateField('Поиск по имени', validators=[v.optional()], default='')
    sort = SelectField(
        'Сортировка',
        choices=[
            ('created', 'По дате создания'),
        ],
        default='created'
    )

class BROrderCreateForm(FlaskForm):
    status = SelectField('', choices=[(x, x) for x in BROrder.STATUSES])
    customer_email = EmailField(validators=[v.Optional()])
    operator_id = SelectField()
    coords_lat = FloatField(validators=[v.InputRequired()])
    coords_lon = FloatField(validators=[v.InputRequired()])
    address = StringField()
    contacts = HiddenField()
    start = StringField()
    tts = IntegerField()
    customer_comment = TextAreaField()
    operator_comment = TextAreaField()
    manager_comment = TextAreaField()

class BROrderAssetEditForm(FlaskForm):
    type = SelectField('', choices=[(x, x) for x in BROrderAsset.TYPES])
    size = IntegerField(validators=[v.Optional()])
    s3key = StringField()
    title = StringField()
    width = IntegerField(validators=[v.Optional()])
    height = IntegerField(validators=[v.Optional()])
    operator_id = SelectField()
    tour_id = IntegerField(validators=[v.Optional()])
    duration = IntegerField(validators=[v.Optional()])
    product_meta = TextAreaField()
    tour_video_id = IntegerField(validators=[v.Optional()])
    preview_s3key = StringField()
    upload_file = FileField(validators=[v.Optional()])

class BROrderAssetFiltersForm(FlaskForm):
    sort = SelectField(choices=[('created', 'дате создания')])
    search = StringField()

class BROfficesFiltersForm(FiltersForm):
    """Фильтр списка офисов"""
    __remember_fields__ = ['sort']

    search = StringField('Поиск по названию', validators=[v.optional()], default='')
    sort = SelectField(
        'Сортировка',
        choices=[
            ('created', 'По дате создания'),
        ],
        default='created'
    )


class BROfficeEditForm(FlaskForm):
    manager_email = StringField('', validators=[v.InputRequired()])
    active = BooleanField('Работает')
    city_id = SelectField(validate_choice=False, validators=[v.InputRequired()], choices=[])
    coords_lat = FloatField(validators=[v.InputRequired()])
    coords_lon = FloatField(validators=[v.InputRequired()])
    address = StringField()
    title = StringField()
    description = TextAreaField()
    manager_comment = TextAreaField()
    work_start = StringField(validators=[v.InputRequired()])
    work_end = StringField(validators=[v.InputRequired()])

class BROperatorsFiltersForm(FiltersForm):
    """Фильтр списка операторов"""

    __remember_fields__ = ['sort']

    search = StringField('Поиск по имени', validators=[v.optional()], default='')
    sort = SelectField(
        'Сортировка',
        choices=[
            ('created', 'По дате создания'),
        ],
        default='created'
    )


class BROperatorEditForm(FlaskForm):
    user_email = StringField('', validators=[v.InputRequired()])
    active = BooleanField('Работает')
    work_start = StringField(validators=[v.InputRequired()])
    work_end = StringField(validators=[v.InputRequired()])
    manager_comment = TextAreaField()