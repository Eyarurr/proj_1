import io
import base64
from collections import OrderedDict

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.hybrid import hybrid_property
from flask_babel import lazy_gettext, gettext
from lagring.assets.image import ImageAsset
from lagring import AssetProcessingException

from visual.core import db, storage
from visual.util import get_lang
from visual.models.tours import Tour, Footage


class Offer(db.Model, storage.Entity):
    """
    Презентация: мультитур, промо-страница или PDF
    """
    __tablename__ = 'offers'

    TYPES = OrderedDict([
        ('multitour', 'Мульти-тур'),
        ('landing', 'Промо-страница'),
        ('pdf', 'PDF-презентация')
    ])

    TEMPLATES = {
        'multitour': OrderedDict([
            ('common', lazy_gettext("Normal")),
            #            ('carousel', 'С каруселью'),
        ]),
        'landing': OrderedDict([
            ('light', lazy_gettext("Light")),
            ('dark', lazy_gettext("Dark"))
        ]),
        'pdf': OrderedDict([
            # id темплейта должен начинаться либо с 'portrait' либо с 'landscape'
            ('portrait1', lazy_gettext("Portrait 1")),
            ('portrait2', lazy_gettext("Portrait 2")),
            ('landscape1', lazy_gettext("Landscape 1")),
            ('landscape2', lazy_gettext("Landscape 2")),
        ])
    }

    # Переменные приходят с формы в template_data
    BOOL_FIELD_NAME = ['keep_position', ]

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), index=True, nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('folders.id', ondelete='CASCADE', onupdate='CASCADE'), index=True, nullable=True)
    type = db.Column(db.Enum(*list(TYPES.keys()), name='offer_type'))
    hidden = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    title_ru = db.Column(db.String(255), nullable=False, default='', server_default='')
    title_en = db.Column(db.String(255), nullable=False, default='', server_default='')
    title_de = db.Column(db.String(255), nullable=False, default='', server_default='')
    title_fr = db.Column(db.String(255), nullable=False, default='', server_default='')

    template = db.Column(db.String(32), nullable=False)
    template_data = db.Column(JSONB)
    logo = ImageAsset(width=300, height=60, transform='fit')  # Логотип в шапке

    cnt_tours = db.Column(db.Integer(), nullable=False, default=0, server_default='0')

    tours = db.relationship('OfferTour', backref='offer', order_by='OfferTour.sort', cascade='all, delete')
    creator = db.relationship('User', foreign_keys=[created_by])
    user = db.relationship('User', foreign_keys=[user_id])
    folder = db.relationship('Folder')

    @classmethod
    def get_title_field(cls):
        return getattr(cls, 'title_' + get_lang())

    @hybrid_property
    def title(self):
        return getattr(self, 'title_' + get_lang())

    @title.setter
    def title(self, value):
        setattr(self, 'title_' + get_lang(), value)

    @property
    def preview(self):
        """Затычка для получения превьюшки презентации. Генерит паразитные запросы :("""
        if self.tours and len(self.tours) > 0:
            return self.tours[0].tour.preview
        return None

    @property
    def screen(self):
        """Затычка для получения заставки презентации. Генерит паразитные запросы :("""
        if self.tours and len(self.tours) > 0:
            return self.tours[0].tour.screen
        return None

    def badge(self):
        """
        Возвращает структуру OfferBadge для API (https://docs.google.com/document/d/11ZjR33CQE-JeHiQrI6jQx4O3D6woXDkNNYxYVLEDk1U/edit#heading=h.w3btvxit8rc7)
        :return: TourBadge
        """
        t = {
            'id': self.id,
            'created': self.created.isoformat(),
            'type': self.type,
            'title': self.title,
            'cnt_tours': self.cnt_tours,
        }
        if self.preview:
            t['preview'] = self.preview.url
        if self.screen:
            t['screen'] = self.screen.url
        t['hidden'] = self.hidden
        return t

    def get_template(self, file=''):
        """Возвращает относительный путь к шаблону презентации."""
        return 'offers/%s/%s/%s' % (self.type, self.template, file)

    def process_editor_json(self, data):
        """Обрабатывает объект, который отдаёт упакованным в JSON редактор презентации.
        Возвращает список ошибок.
        """
        if not self.template_data:
            self.template_data = {}

        errors = []
        for k in data.keys():
            # Ищем, нет ли ассетов в форме
            if k.startswith('asset:') and len(data[k]) > 0:
                asset_name = k[6:]

                if not hasattr(self, asset_name):
                    errors.append(lazy_gettext("System error (BAD_ASSET_NAME %(name)s)", name=asset_name))
                    continue

                try:
                    setattr(self, asset_name, io.BytesIO(base64.b64decode(data[k][0]['body'])))
                except AssetProcessingException:
                    errors.append(lazy_gettext("Unable to upload an image %(name)s", name=asset_name))
                    continue
            else:
                self.template_data[k] = data[k]

        for field_name in self.BOOL_FIELD_NAME:
            self.template_data[field_name] = self.template_data.get(field_name, 'off') == 'on'

        flag_modified(self, 'template_data')
        return errors

    def __str__(self):
        return '<Offer#%r %r/%r %r>' % (self.id, self.type, self.template, self.title_ru)


class OfferTour(db.Model):
    __tablename__ = 'offer_tours'

    offer_id = db.Column(db.Integer(), db.ForeignKey('offers.id', ondelete='CASCADE', onupdate='CASCADE'),
                         primary_key=True)
    tour_id = db.Column(db.Integer(), db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'),
                        primary_key=True)
    sort = db.Column(db.SmallInteger(), nullable=False, default=0, server_default='0')
    title = db.Column(db.String(255))

    tour = db.relationship('Tour', lazy='joined')

    def __repr__(self):
        return '<OfferTour %d: %d->%d "%s">' % (self.sort or 0, self.offer_id or 0, self.tour_id or 0, self.title)

    def api_repr(self):
        return {
            'offer_id': self.offer_id,
            'tour_id': self.tour_id,
            'sort': self.sort,
            'title': self.title
        }


class OfferChangedJurisdiction(db.Model):
    """Смена юрисдикции мультитурами"""
    __tablename__ = 'offers_changed_jurisdiction'

    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    local_id = db.Column(db.Integer(), primary_key=True, nullable=False)
    remote_id = db.Column(db.Integer(), nullable=False)
    moved_to = db.Column(db.Text(), nullable=False)
