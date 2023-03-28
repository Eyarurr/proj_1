import datetime
import os
import shutil
from sqlalchemy.orm.attributes import flag_modified
import boto3

from visual import create_app
from visual.core import db
from visual.models import User, Tour, AuthToken, Footage, Tag, Estate, EstateTag
from visual.util import unzip_footage_tour


# Кеш для set_flow() со значением FLOW_UPLOAD_TMP_DIR из конфига, чтобы не создавать Flask-приложение
# при каждом вызове. Криво, но решает проблему огромного количества создаваемых приложений.
_CACHE_FLOW_UPLOAD_TMP_DIR = None


def set_flow(files, overwrite=False):
    """
    Заполняет директорию config['FLOW_UPLOAD_TMP_DIR'] файлами из files:
    {
        'TOKEN1': ['src/panorama.png'],
        'TOKEN2': ['src/256x256.jpg', 'src/1536x1536.jpg']
    }
    :param overwrite: bool переписывать ли существующие файлы
    :param files: dict
    :return:
    """
    global _CACHE_FLOW_UPLOAD_TMP_DIR
    if _CACHE_FLOW_UPLOAD_TMP_DIR is None:
        app = create_app('config.test.py')
        with app.app_context():
            _CACHE_FLOW_UPLOAD_TMP_DIR = app.config['FLOW_UPLOAD_TMP_DIR']
    pd = _CACHE_FLOW_UPLOAD_TMP_DIR
    for token, sources in files.items():
        os.makedirs(os.path.join(pd, token), exist_ok=True)
        for src in sources:
            filename = os.path.basename(src)
            dst = os.path.join(pd, token, filename)
            if overwrite is False and os.path.exists(dst):
                continue
            shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), src), dst)


def create_users(users):
    """
    @param users: {id: {email, name, ...}}
    Создаёт юзеров и даёт им авторизационные токены
    """
    for id_, props in users.items():
        user = User(id=id_, email_confirmed=True, **props)
        user.auth_tokens.append(
            AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30), ip='0.0.0.0'))
        db.session.add(user)


def create_s3_objects(app, files):
    """
    @param files: {key: (filename, mime), ...}
    Заливает в S3 файлы из директории src
    """
    s3 = boto3.resource('s3', endpoint_url=app.config['S3_ENDPOINT_URL'])
    s3bucket = s3.Bucket(app.config['S3_BUCKET'])
    for key, (filename, mime) in files.items():
        print(f'Uploading {filename} to S3 {key}')
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src', filename)
        with open(src, 'rb') as fh:
            s3bucket.put_object(Key=key, Body=fh, ACL='public-read', ContentType=mime)


def create_tours_footages_various_types(user_id, tour_meta=None, footage_meta=None, create_user=False, ):
    """
    Создадим туры и съемки всех возможных сочетаний type и status
    """
    statuses = Footage.STATUSES
    types = Footage.TYPES
    user = db.session.query(User).get(user_id)
    if not user:
        if create_user:
            user = User(id=100, name='footage_type', email='footage_type@biganto.com', email_confirmed=True)
            db.session.add(user)
            db.session.flush()
            user.auth_tokens.append(
                AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30),
                          ip='0.0.0.0'))
            db.session.commit()
        else:
            raise Exception('User не найден')
    ind = 0
    for status in statuses:
        for type in types:
            tour = Tour(user_id=user.id, title=f'tour_{status}_{type}', meta={},
                        footage=Footage(user_id=user.id, _status=status, type=type, meta={}))
            db.session.add(tour)
            db.session.flush()
            if tour_meta:
                tour.meta.update(tour_meta)
                flag_modified(tour, 'meta')
            if footage_meta:
                tour.footage.meta.update(footage_meta)
                flag_modified(tour.footage, 'meta')
            ind += 1
    db.session.commit()

    # Так как tours.id и footage.id ID могли быть указаны в tours.json принудительно, обновим секвенции
    # tours_id_seq и footage_id_seq


def create_tags(user_id, data):
    """Создаёт теги из списка [{name, prefix, suffix, display_dict}, ...] или просто [name, ...] для юзера user_id
    Возвращает словарь {tag_name: tag_id, ...}"""
    tags = []
    for d in data:
        if type(d) is dict:
            tag = Tag(user_id=user_id, **d)
        else:
            tag = Tag(user_id=user_id, name=d)
        tags.append(tag)

    db.session.add_all(tags)
    db.session.flush()

    return {tag.name: tag.id for tag in tags}


def create_estate(data, tags):
    """Создаёт эстейт из структуры
    {
        id
        user_id
        title
        tags: {
            name: value
        }
    }
    В `tags` ожидает увидеть словарь {tag_name: tag_id, ...}
    """
    if 'tags' in data:
        etags = data.pop('tags')
    else:
        etags = []
    estate = Estate(**data)
    db.session.add(estate)
    for tag_name, val in etags.items():
        estate.tags.append(EstateTag(tag_id=tags[tag_name], value=val))
