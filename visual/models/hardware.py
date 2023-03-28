from collections import OrderedDict

from lagring.assets.image import ImageAsset

from visual.core import db, storage


class Hardware(db.Model, storage.Entity):
    __tablename__ = 'hardwares'

    HARDWARE_LOCATIONS = OrderedDict([
        ('storage', 'На складе в офисе'),
        ('home', 'У сотрудника дома'),
        ('office', 'У сотрудника на столе'),
    ])

    HARDWARE_TYPES = OrderedDict([
        ('1', 'Монитор'),
        ('2', 'Клавиатура'),
        ('3', 'Мышь'),
        ('4', 'Системный блок'),
        ('5', 'Планшет'),
        ('6', 'Смартфон'),
        ('7', 'Аксессуар'),
        ('8', 'VR очки'),
        ('9', 'Флешка'),
        ('10', 'Жесткий диск'),
        ('11', 'Кардборд'),
        ('12', 'Фотоаппарат'),
        ('13', 'Ноутбук'),
        ('14', 'Другое'),
    ])

    id = db.Column(db.Integer(), nullable=False, primary_key=True)
    sn = db.Column(db.String(255))
    title = db.Column(db.String(255))
    type = db.Column(db.Enum(*list(HARDWARE_TYPES.keys()), name='hardware_type'), nullable=False, default='1',
                     server_default='1')
    description = db.Column(db.Text())
    price = db.Column(db.Integer(), nullable=True)
    location = db.Column(db.Enum(*list(HARDWARE_LOCATIONS.keys()), name='hardware_location'), nullable=False,
                         default='storage', server_default='storage')
    buy_date = db.Column(db.Date(), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'), nullable=True,
                        index=True)
    preview = ImageAsset(width=150, height=100, transform='fit')
    photo = ImageAsset(width=800, height=600, transform='fit', constraint_type='min', size_constraint=(800, 600))
    user = db.relationship('User', foreign_keys=[user_id])
    hardware_event = db.relationship('HardwareEvent', backref='hardware', cascade='all, delete-orphan, delete')

    def get_location(self):
        return self.HARDWARE_LOCATIONS.get(self.location, '')

    def get_type(self):
        return self.HARDWARE_TYPES.get(self.type, '')

    def view_api(self):
        result = {
            'sn': self.sn,
            'title': self.title,
            'type': self.get_type(),
            'location': self.location,
            'get_location': self.get_location(),
            'user_id': self.user_id,
            'user': self.get_user(),
            'price': self.price,
            'preview': self.preview.url,
            'description': self.description,
        }
        return result

    def get_user(self):
        if self.user_id != None:
            return self.user.name
        else:
            return None


class HardwareEvent(db.Model, storage.Entity):
    __tablename__ = 'hardwares_events'

    id = db.Column(db.Integer(), nullable=False, primary_key=True, autoincrement=True)
    hardware_id = db.Column(db.Integer(), db.ForeignKey('hardwares.id', ondelete='CASCADE', onupdate='CASCADE'),
                            primary_key=True)
    key_date = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='NO ACTION', onupdate='NO ACTION'))
    location = db.Column(db.Text())

    user = db.relationship('User', foreign_keys=[user_id])

    def get_location(self):
        return Hardware.HARDWARE_LOCATIONS.get(self.location, '')
