from lagring.assets.image import ImageAsset

from visual.core import db, storage


class Partner(db.Model, storage.Entity):

    __tablename__ = 'partners'

    id = db.Column(db.Integer, primary_key=True)
    logo = ImageAsset()
    sort = db.Column(db.SmallInteger, nullable=False, default=0, server_default='0')
    hidden = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    title = db.Column(db.String(255))
    url = db.Column(db.String(255))
