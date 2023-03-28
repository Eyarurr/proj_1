from flask_wtf import FlaskForm
from wtforms import validators as v, DateField
from wtforms import SelectField, IntegerField, StringField, TextAreaField, FileField
from visual.models import EstateAsset, Tour, TourVideo

def validate_tour(form, field):
    if form.type.data == 'tour':
        tour = Tour.query.get(field.data)
        if not tour:
           field.errors.append(f'Указан id несуществующего тура: {field.data}')
            
def validate_tour_video(form, field):
    if form.type.data == 'tour_video':
        tour_video = TourVideo.query.get(field.data)
        if not tour_video:
            field.errors.append(f'Указан id несуществующего tour_video: {field.data}')


class EstateAssetEditForm(FlaskForm):
    type = SelectField('', choices=[(x, x) for x in EstateAsset.TYPES])
    size = IntegerField(validators=[v.Optional(), ])
    s3key = StringField()
    title = StringField()
    width = IntegerField(validators=[v.Optional()])
    height = IntegerField(validators=[v.Optional()])
    tour_id = IntegerField(validators=[v.Optional(), validate_tour])
    duration = IntegerField(validators=[v.Optional()])
    product_meta = TextAreaField()
    tour_video_id = IntegerField(validators=[v.Optional(), validate_tour_video])
    preview_s3key = StringField()
    upload_file = FileField(validators=[v.Optional()])


class EtagEditForm(FlaskForm):
    tag_id = SelectField('',)
    value = StringField()


class FormTag(FlaskForm):
    name = StringField()
    display_dict = TextAreaField()
    prefix = StringField()
    suffix = StringField()
    crm_key = StringField()
    label = StringField()


class AddEstateForm(FlaskForm):
    user_id = IntegerField(validators=[v.Optional()])
    title = StringField()
    remote_id = IntegerField(validators=[v.Optional()])
    synced = DateField(validators=[v.Optional()])


class FilterEstatesForm(FlaskForm):
    search = StringField()
    sort = SelectField(choices=(('дате создания','дате создания'),))
    select = SelectField(choices=[('title', 'названию'),('id', 'id'),('user_name', 'юзеру')])


class FilterEtagForm(FlaskForm):
    search = StringField()
    sort = SelectField(choices=(('дате создания','дате создания'),))
    select = SelectField(choices=[('label', 'лейблу'), ('name', 'имени'), ('value', 'значению')])


class EstatesAssetsFilterForm(FlaskForm):
    search = StringField()
    sort = SelectField(choices=(('дате создания', 'дате создания'),))
    
    
class SelectEstatesForm(FlaskForm):
    parent_id = SelectField()