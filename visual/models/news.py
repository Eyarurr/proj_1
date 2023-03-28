from lagring.assets.image import ImageAsset
from visual.core import db, storage


class NewsArticle(db.Model):
    __tablename__ = 'news'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text(), nullable=False, default='', server_default='')

    author = db.relationship('User')


class NewsFeed(db.Model, storage.Entity):
    __tablename__ = 'feeds'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    hidden = db.Column(db.Boolean, nullable=False, default=False)
    original = ImageAsset()
    preview = ImageAsset(width=330, height=219, transform='crop')


class NewsFeedTranslation(db.Model):
    __tablename__ = 'feeds_translations'

    id = db.Column(db.Integer(), primary_key=True)
    lang = db.Column(db.String(2), nullable=False, default='en')
    published = db.Column(db.Boolean, nullable=False, default=True)
    title = db.Column(db.String(255), nullable=False, default='')
    announce = db.Column(db.String(255), nullable=False, default='')
    text = db.Column(db.Text(), nullable=False, default='')
    feed_id = db.Column(db.Integer(), db.ForeignKey('feeds.id', ondelete='CASCADE', onupdate='CASCADE'))


class NewsPhoto(db.Model, storage.Entity):
    __tablename__ = 'feeds_photos'

    id = db.Column(db.Integer(), primary_key=True)
    hidden = db.Column(db.Boolean, nullable=False, default=False)
    feed_id = db.Column(db.Integer(), db.ForeignKey('feeds.id', ondelete='CASCADE', onupdate='CASCADE'))
    original = ImageAsset()
    preview = ImageAsset(width=330, height=219, transform='crop')
    image = ImageAsset(width=1400, height=1400, transform='fit')


class NewsPhotoTranslation(db.Model, storage.Entity):
    __tablename__ = 'feeds_photos_translations'

    id = db.Column(db.Integer(), primary_key=True)
    lang = db.Column(db.String(2), nullable=False, default='en')
    title = db.Column(db.String(255), nullable=False, default='')
    photo_id = db.Column(db.Integer(), db.ForeignKey('feeds_photos.id', ondelete='CASCADE', onupdate='CASCADE'))
