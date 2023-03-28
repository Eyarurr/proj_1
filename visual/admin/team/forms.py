from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, ValidationError, BooleanField, SelectField, DateField, FileField, \
    SelectMultipleField
from wtforms.fields import EmailField
from wtforms import validators as v
from visual.util import PhoneField, MultiCheckboxField, FiltersForm
from visual.models import User, TeamMember
from visual.util import FiltersForm, SwitchWidget


def strip(t):
    if isinstance(t, str):
        return t.strip()
    return t


class TeamMemberForm(FlaskForm):
    roles = MultiCheckboxField('Роли')
    department_id = SelectField('Отдел', coerce=int, validators=[v.data_required('Заполните поле "Отдел"')])
    position = StringField('Должность')
    description = TextAreaField('Описание')
    phone_mobile = StringField('Мобильный телефон')
    phone_internal = StringField('Внутренний телефон')
    telegram = StringField('Никнейм в телеграмме')
    city_id = SelectField('Город', validators=[v.optional()], validate_choice=False)
    timezone = SelectField('Временная зона')
    office_days = SelectField('Сколько дней в офисе.(0 — полная удалёнка, 5 — полный день)',
                              choices=[(5, 'фуллтайм'), (4, '4'), (3, '3'), (2, '2'), (1, '1'),
                                       (0, 'полная удалёнка')], coerce=int)
    location_url = StringField('Где сидит')
    birthdate = DateField('Дата рождения', format='%Y-%m-%d', validators=[v.optional()])
    photo_ = FileField('Фотография')
    hired = DateField('Принят', format='%Y-%m-%d', validators=[v.optional()])
    fired = DateField('Уволен', format='%Y-%m-%d', validators=[v.optional()])


class TeamStatusesForm(FlaskForm):
    start = DateField('Начало отпуска/больничного', format='%Y-%m-%d',
                      validators=[v.data_required('Поле обязательно для заполнения')])
    finish = DateField('Конец отпуска/больничного', format='%Y-%m-%d', validators=[v.optional()])
    comment = StringField()
    type = SelectField(
        choices=[('', ''), ('vacation', 'отпуск'), ('sick-leave', 'больничный'), ('maternity-leave', 'декретный'),
                 ('business-trip', 'командировка'), ('other', 'прочие')],
        validators=[v.data_required('Поле обязательно для заполнения')], default='vacation')


class TeamUserForm(FlaskForm):
    name = StringField('Имя', validators=[v.data_required('Задайте, пожалуйста, имя')], filters=[strip])
    email = EmailField('E-mail', validators=[v.data_required('Обязательно нужно ввести e-mail')], filters=[strip])
    password = StringField('Пароль', filters=[strip])
    banned = BooleanField('Забанен')


class TeamFiltersForm(FiltersForm):
    """Фильтр списка сотрудников"""

    __remember_fields__ = ['sort', 'display']

    search = StringField('Поиск по имени или e-mail', validators=[v.optional()], default='')
    sort = SelectField(
        'Сортировка',
        choices=[
            ('created', 'Дате создания'),
            ('name', 'Имени'),
            ('position', 'Должности'),
            ('last_active', 'Времени последнего визита'),
            ('expirience', 'Стажу'),
            ('age', 'Возрасту'),
        ],
        default='name'
    )
    display = SelectField('Показывать', choices=[('thumbnails', 'Плитка'), ('table', 'Таблица')],
                          default='table', widget=SwitchWidget())
