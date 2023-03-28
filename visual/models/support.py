from collections import OrderedDict

from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from lagring import Asset

from visual.core import db, storage
from visual.util import now


class Issue(db.Model):
    __tablename__ = 'issues'

    STATUSES = OrderedDict([
        ('new', 'Новый'),
        ('process', 'В работе'),
        ('complete', 'Готово'),
        ('spam', 'Спам'),
    ])

    SUBJECTS = OrderedDict([
        ('tour', 'Проблемы с туром'),
        ('payment', 'Оплата и тарифы'),
        ('feedback', 'Обратная связь'),
        ('other', 'Другое'),
    ])

    id = db.Column(db.Integer(), primary_key=True)
    status = db.Column(db.Enum(*list(STATUSES.keys()), name='issue_status'), nullable=False, default='new', server_default='new')
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    number = db.Column(db.String(255), nullable=False)

    subject = db.Column(db.Enum(*list(SUBJECTS.keys()), name='issue_subject'), nullable=False, server_default='other', default='other')
    tour_link = db.Column(db.String(2048))
    text = db.Column(db.Text())
    contact_email = db.Column(db.String(255))

    # Юзер, который создал тикет.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT', onupdate='CASCADE'), index=True)

    user = db.relationship('User', foreign_keys=[user_id], backref='issues')

    def __repr__(self):
        return '<Issue %d:%s>' % (self.id, self.created)


class SoftwareVersion(db.Model, storage.Entity):
    __tablename__ = 'software_versions'
    __table_args__ = (db.Index('app_id', 'version'),)

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'))
    app_id = db.Column(db.String(), nullable=False)
    version = db.Column(ARRAY(db.Integer(), zero_indexes=True))
    download_url = db.Column(db.Text())
    filename = db.Column(db.String())
    filesize = db.Column(db.Integer())

    file = Asset()
    creator = db.relationship('User', foreign_keys=[created_by])


class SoftwareDistributionKey(db.Model):
    __tablename__ = 'software_distribution_keys'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    app_id = db.Column(db.CHAR(16), nullable=False, index=True)
    used = db.Column(db.DateTime(timezone=True), server_default=None, nullable=True)
    used_by = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'), nullable=True)
    key = db.Column(db.Text(), nullable=False)

    __table_args__ = (db.Index('ix_app_id_key', 'app_id', 'key'),)
