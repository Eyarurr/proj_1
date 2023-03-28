from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, FileField, BooleanField, IntegerField, HiddenField, \
    RadioField, validators as v, PasswordField
from visual.models import Footage, Tour
from visual.util import FiltersForm, SwitchWidget


class ToursFilter(FiltersForm):
    __remember_fields__ = ['sort']

    type = SelectField('Тип', choices=[('', 'Все типы')] + list(Footage.TYPES.items()), default='')
    status = SelectField('Статус', choices=[('', 'Все статусы')] + list(Footage.STATUSES.items()), default='')
    feature = SelectField('С фичей', choices=[
        ('', 'Любые фичи'),
        ('active_meshes', 'С активными мешами'),
        ('overlays', 'С оверлеями'),
        ('dollhouse', 'С доллхаусом'),
        ('walk', 'С маршрутом'),
        ('audio', 'С озвучкой'),
        ('binocular', 'Бинокулярные'),
        ('toolbar', 'С кастомным тулбаром'),
        ('navigator', 'С навигатором'),
        ('external_meta', 'С внешней метой'),
        ('branding', 'С брендингом'),
        ('blotch', 'С нашлёпкой'),
        ('clickable', 'С кликабельными объектами'),
        ('shadows', 'С тенями'),
        ('with_password', 'С паролем'),
        ('no_minimap', 'Без миникарты'),
    ], default='')
    folder_id = SelectField('Папка', default='', choices=[('', 'Все папки'), ('0', 'Корень')])
    search = StringField('Поиск по названию')
    sort = SelectField('Сортировка', choices=[('created', 'Во времени создания'), ('title', 'По имени тура'), ('folder', 'По имени папки и тура')], default='created')


class ToursMovedFilter(FiltersForm):
    search_by = SelectField('Искать по', default='', choices=[
        ('', 'Искать по'),
        ('local_id', 'По id тура'),
        ('remote_id', 'По новому id тура'),
        ('created', 'По дате переноса'),
        ('server', 'Куда перенесен'),
    ])
    search_field = StringField('Поиск ', )

class TourForm(FlaskForm):
    footage_status = SelectField('Статус', choices=[])
    hidden = BooleanField('Скрыто')
    folder_id = SelectField('Папка')
    title = StringField('Название')
    screen = FileField('Обложка')
    gallery_admin = SelectField('Показывать в галерее', choices=[(str(k), v) for k, v in Tour.GALLERY_OPTIONS.items()])
    password_clear = BooleanField('Убрать пароль')
    password = PasswordField('Пароль на тур')
    password_in_url = BooleanField('Можно передавать пароль в Query String')
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


class TourUploadForm(FlaskForm):
    type = SelectField('Тип', choices=list(Footage.TYPES.items()), default='real', validators=[v.data_required('Нужно указать тип.')])
    title = StringField('Название', validators=[v.optional()])
    folder_id = SelectField('Папка')
    status = SelectField('Папка', choices=list(Footage.STATUSES.items()), default='testing')
    filename = HiddenField('Архив', validators=[v.data_required('Архив не загрузился.')])
    passway_calc = BooleanField('Просчитать граф достижимости')
    model_size = BooleanField('Вычислить вес модели')
