from __future__ import annotations
import base64
import hmac
import hashlib
import string
import random
from collections import OrderedDict
from datetime import date, datetime, timedelta
from urllib.parse import urljoin
import logging
import secrets
import requests
import os
import inspect

from requests import ReadTimeout, ConnectionError
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, INET
from sqlalchemy.orm.attributes import flag_modified
from flask import current_app, url_for, g, render_template_string, abort
from flask_login import current_user
from flask_babel import gettext
from lagring.assets.image import ImageAsset
import stripe
import iniconfig

from visual.core import db, storage, products
from visual.models.tours import Footage
from visual.models.user_settings import UserSettings
from visual.mail import send_email
from visual.util import strip_html


class User(db.Model, storage.Entity):
    __tablename__ = 'users'

    CONTACT_TYPES = {
        'phone': 'Телефон',
        'phone.cell': 'Мобильный телефон',
        'phone.work': 'Рабочий телефон',
        'phone.home': 'Домашний телефон',
        'telegram': 'Телеграм',
        'whatsapp': 'WhatsApp',
        'viber': 'Viber',
        'link': 'Ссылка',
        'instagram': 'Instagram',
        'facebook': 'Facebook',
        'vk': 'ВКонтакте',
        'linkedin': 'LinkedIn',
        'youtube': 'YouTube',
        'description': 'Описание',
        'profession': 'Профессия'
    }

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'))
    last_active = db.Column(db.DateTime(timezone=True), nullable=True)
    banned = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    deleted = db.Column(db.DateTime(timezone=True))  # Время, когда юзер самоубился

    name = db.Column(db.String(255), nullable=False, default='')
    email = db.Column(db.String(255), nullable=False, unique=True)
    email_confirmed = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    password_hash = db.Column(db.String(255))

    stripe_customer_id = db.Column(db.String(64))

    admin_comment = db.Column(db.Text())

    # Отправлять ли уведомления по почте, 0 - никакие, 1 - все.
    email_notifications = db.Column(db.SmallInteger(), default=1, server_default='1')

    settings = db.Column(JSONB, nullable=False, default={}, server_default='{}')
    _timezone = db.Column(db.String(25), nullable=True)
    lang = db.Column(db.String(2))

    avatar = ImageAsset(width=192, height=192, transform='crop')
    contacts = db.Column(JSONB, nullable=False, default={}, server_default='{}')

    team_status = db.relationship('TeamMemberStatus', back_populates='user', uselist=True)
    team_member = db.relationship('TeamMember', back_populates='user', uselist=False, cascade='save-update, merge, delete, delete-orphan', single_parent=True)
    creator = db.relationship('User', remote_side=id)
    folders = db.relationship('Folder', backref='user', order_by='Folder.title', cascade='save-update, merge, delete, delete-orphan')
    user_products = db.relationship('UserProduct', backref='user', cascade='save-update, merge, delete, delete-orphan')

    auth = db.relationship('UserAuth', backref='user', cascade='save-update, merge, delete, delete-orphan')

    # Кэш для User.settings_obj
    _settings = None
    _cached_count_footages = None

    def __repr__(self):
        return '<User %d:%s>' % (0 if self.id is None else self.id, self.name)

    @staticmethod
    def hash_password(data):
        return hashlib.md5((data + current_app.config['SECRET_KEY']).encode()).hexdigest()

    def get_api_auth_signature(self):
        """
        Возвращает подпись токена для авторизации через API
        """
        key = current_app.config.get('SECRET_KEY')
        payload = '{}:{}:{}'.format(self.id, self.email, self.password_hash)
        return base64.urlsafe_b64encode(
            hmac.new(key.encode('utf-8'), payload.encode('utf-8'), hashlib.sha512).digest()
        ).decode()

    def get_api_auth_token(self):
        """
        Возвращает авторизационный токен для API (клиентская сессия)
        """
        return '{}|{}'.format(self.id, self.get_api_auth_signature())

    @classmethod
    def load_from_api_token(cls, token):
        """
        Авторизация по токену API. Ищет пользователя по токену, проверяет его на паршивость.
        Возвращает кортеж из экземпляра юзера и None, None, если всё хорошо и кортеж из None, кода текста ошибки,
        если всё плохо.
        :param token: Авторизационный токен
        :return: (User, error_code, error_message)
        """
        from visual.api_deprecated import errors

        if token.startswith('X|'):
            # Токен серверной сессии, X|{AuthToken.id}|{AuthToken.signature}
            try:
                token_id, signature = AuthToken.parse_token(token)
            except ValueError:
                return None, errors.AUTH_BAD_TOKEN, 'Bad auth_token.'

            res = db.session \
                .query(User, AuthToken) \
                .join(User) \
                .filter(AuthToken.id == token_id, AuthToken.signature == signature, AuthToken.expires >= db.func.now()) \
                .first()
            if not res:
                return None, errors.AUTH_USER_NOT_FOUND, 'Token is invalid.'

            user, auth_token = res
        else:
            # Токен клиентской сессии, {User.id}|{b64(sha512(SECRET_KEY, {id}:{email}:{password}))
            x = token.split('|', 1)
            if len(x) < 2:
                return None, errors.AUTH_BAD_TOKEN, 'Bad auth_token.'
            user_id, signature = x
            if not user_id.isnumeric():
                return None, errors.AUTH_BAD_TOKEN, 'Bad auth_token.'
            user = cls.query.filter_by(id=user_id).first()
            if not user:
                return None, errors.AUTH_USER_NOT_FOUND, 'User {} not found.'.format(user_id)
            if user.get_api_auth_signature() != signature:
                return None, errors.AUTH_BAD_SIGNATURE, 'Wrong signature.'

        if user.banned:
            return None, errors.AUTH_USER_BANNED, 'User banned.'
        if not user.email_confirmed:
            return None, errors.AUTH_USER_EMAIL_NOT_CONFIRMED, 'User email not confirmed.'
        if not user.is_active:
            return None, errors.AUTH_USER_BANNED, 'User is deactivated.'

        return user, None, None

    def get_valid_auth_token(self, create=False):
        """
        Находит активный авторизационный токен и возвращает его или None, если таковой не найден.
        При create=True, если токен не найден, он создаётся и записывается в базу.
        """
        token = AuthToken.query.filter(AuthToken.user_id == self.id, AuthToken.expires >= db.func.now()).first()

        if token is None and create is True:
            token = AuthToken(
                user_id=self.id,
                ip='0.0.0.0',
                expires=datetime.now() + timedelta(days=30),
                signature=AuthToken.generate(),
                title='generated by User.get_valid_auth_token()'
            )
            db.session.add(token)
            db.session.commit()

        return token

    @property
    def is_active(self):
        return not self.banned and self.email_confirmed

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return not self.is_authenticated

    def get_id(self):
        return str(self.id)

    def has_role(self, *args):
        """Возвращает True, если пользователь — сотрудник, и у него есть хотя бы одна роль из указанных в *args,
        или он суперюзер. У удалённых юзеров ролей типа нет."""
        if not self.team_member:
            return False

        if self.deleted:
            return False

        if 'super' in self.team_member.roles:
            return True

        for role in args:
            if role in self.team_member.roles:
                return True

        return False

    @property
    def unsubscribe_token(self):
        return hashlib.md5('{}{}{}'.format(self.created, self.email, self.password_hash).encode('utf-8')).hexdigest()

    def unsubscribe_link(self, list_id):
        return url_for('front.unsubscribe', user=self.id, list=list_id, token=self.unsubscribe_token)

    @property
    def timezone(self):
        return self._timezone

    @timezone.setter
    def timezone(self, value):
        if value in current_app.config['TIMEZONES']:
            self._timezone = value

    def guess_lang(self):
        """Если у юзера не сохранён язык, то угадывает его по g.lang, или возвращает дефолтный"""
        if self.lang:
            return self.lang

        return g.get('lang', current_app.config['LANGUAGE'])

    @property
    def settings_obj(self):
        if self._settings is None:
            self._settings = UserSettings(**(self.settings or {}))
        return self._settings

    def settings_save(self):
        self.settings = self.settings_obj.dict(exclude_defaults=True)
        flag_modified(self, 'settings')

    def as_dict(self):
        """DEPRECATED. Возвращает словарь с основными своими свойствами"""
        return {
            'id': self.id,
            'created': self.created.isoformat(),
            'name': self.name,
            'email': self.email,
            'products': {},
            # Legacy, deprecated
            'plan_id': self.products['virtoaster'].plan_id if 'virtoaster' in self.products else None,
        }

    def api_repr(self, **kwargs):
        res = {
            'id': self.id,
            'name': self.name,
            'avatar': self.avatar.url if self.avatar else None,
            'contacts': self.contacts
        }
        return {**res, **kwargs}

    def current_user_api_repr(self, _settings_no_default=False, **kwargs):
        if not current_user.is_authenticated or current_user.id != self.id:
            return {}

        res = {**self.api_repr(), **{
            'created': self.created,
            'email': self.email,
            'email_notifications': self.email_notifications,
            'timezone': self.timezone,
            'deleted': self.deleted,
            'banned': self.banned,
            'settings': self.settings_obj.as_dict(_settings_no_default),
            'products': {}
        }}

        for product_id, product in self.products.items():
            res['products'][product_id] = product.dict()

        if self.team_member:
            res['team_member'] = {
                'department': None if self.team_member.department_id is None else {
                    'id': self.team_member.department_id,
                    'title': self.team_member.department.title,
                },
                'position': self.team_member.position,
                'roles': self.team_member.roles
            }
        else:
            res['team_member'] = None

        return {**res, **kwargs}

    def purge_timedelta(self):
        """Возвращает datetime.timedelta, через которое удалённый аккаунт будет удалён навсегда.
        Если аккаунт не удалён, то возвращает None."""
        if self.deleted is None:
            return None
        return timedelta(days=current_app.config['DELETED_USER_AGONY_DUR'] + 1) - (
                datetime.now(tz=self.deleted.tzinfo) - self.deleted)

    def count_footages(self):
        """Возвращает количество съёмок пользователя. Значение кешируется в экземпляре класса."""
        if self._cached_count_footages is None:
            self._cached_count_footages = db.session.query(db.func.count(db.distinct(Footage.id))) \
                                              .filter(Footage.user_id == self.id) \
                                              .filter(Footage.status.in_(['published', 'testing', 'banned'])) \
                                              .filter(Footage.type.in_(['virtual'])) \
                                              .scalar() or 0
        return self._cached_count_footages

    def tours_limit(self):
        """Возвращает максимальное количество туров, которое может иметь пользователь.
        Считается из лимитов подключенных продуктов."""
        if 'virtoaster' in self.products:
            return products.virtoaster.plans[self.products['virtoaster'].plan_id].meta['storage']
        return 0

    def set_virtoaster_plan(self, plan_id):
        """
        DEPRECATED!!!

        Ставит юзеру в продукте `virtoaster` план plan_id и лимиты, соответствующие этому плану.
        Создаёт инстанс PlanHistory, если self.id != False (инстанс или загружен, или помещён в базу).
        Не совершает коммита."""
        plan = products['virtoaster'].plans[plan_id]
        if 'virtoaster' not in self.products:
            self.products['virtoaster'] = UserProduct(user_id=self.id, product_id='virtoaster', meta={})
            db.session.add(self.products['virtoaster'])
        self.products['virtoaster'].plan_id = plan_id
        self.products['virtoaster'].meta['processings_left'] = plan.meta['processings']
        flag_modified(self.products['virtoaster'], 'meta')

        if self.id:
            hist = UserPlanHistory(user_id=self.id, product_id='virtoaster', plan_id=plan_id)
            db.session.add(hist)

    def set_product_plan(self, product_id, plan_id):
        """Изменяет свойства продукта или создаёт его, если у юзера его не было."""
        raise NotImplementedError

    def stripe_get_customer(self, create=False):
        """Получает из Stripe объект Customer для этого юзера и возвращает его.
        Если у юзера нет Customer, то при create=True создаст его, запишет в stripe_customer_id и сделает коммит,
        а при create=False вернёт None.
        Ошибки пишет в logger 'billing'."""
        try:
            if not self.stripe_customer_id:
                if create:
                    customer = stripe.Customer.create(
                        email=self.email,
                        name=self.name,
                        description=self.name,
                        metadata={
                            'user_id': self.id,
                        }
                    )
                    self.stripe_customer_id = customer.id
                    db.session.commit()
                else:
                    return None
            else:
                customer = stripe.Customer.retrieve(self.stripe_customer_id)
        except stripe.error.InvalidRequestError as e:
            log_billing = logging.getLogger('billing')
            log_billing.error(
                'User.stript_get_customer({u.email} (u.stripe_customer_id), create={}): API error: {}'.format(str(e),
                                                                                                              create,
                                                                                                              u=self),
                exc_info=True)
            raise

        return customer

    def octobat_get_cusomer(self):
        """Получает из Octobat объект пользователя Octobat, который уникально привязан к Stripe через
        идентификатор пользователя Stripe cus_xxxxxx, и возвращает его.
        """
        if self.stripe_customer_id:
            try:
                response = requests.get(
                    urljoin(current_app.config.get('OCTOBAT_API_URL'), 'customers'),
                    params={'source': self.stripe_customer_id},
                    auth=(current_app.config.get('OCTOBAT_SK'), '')
                )
                if response.status_code == 200:
                    customer = response.json().get('data', [])
                    customer = customer[0] if customer else None
                else:
                    customer = response.json()
            except (ReadTimeout, ConnectionError) as e:
                log_billing = logging.getLogger('billing')
                log_billing.error(
                    'User.octobat_get_customer({u.email} {u.stripe_customer_id}): API error: {}'.format(str(e), u=self),
                    exc_info=True)
                raise
            return customer
        else:
            return None

    def notifications_unseen(self):
        """Возвращает количество непросмотренных нотификаций пользователя."""
        unseen = db.session.query(db.func.count('*')).filter(Notification.user_id == self.id, Notification.seen == None).scalar()

        return unseen or 0

    def notify(self, template=None, template_context=None, channel=None, tone=None, message=None, link=None,
               email_subject=None, email_html=None, email_text=None):
        """Отправляет юзеру нотификацию.
        Возвращает нотификацию (экземпляр класса Notification)"""
        if template_context is None:
            template_context = {}

        if template is not None:
            template_file = os.path.join(current_app.root_path, current_app.template_folder, 'notifications', template + '.nfc')
            ini = iniconfig.IniConfig(template_file)

            if 'user' not in template_context:
                template_context['user'] = self
        else:
            ini = {}

        if channel is None:
            channel = ini['COMMON']['channel']
        if tone is None:
            tone = ini['COMMON']['tone']
        if link is None:
            link = render_template_string(ini['COMMON']['link'], **template_context)

        lang = self.guess_lang().upper()
        if lang not in ini:
            lang = 'EN'

        if message is None:
            message = render_template_string(ini[lang]['message'], **template_context)

        notification = Notification(
            user_id=self.id,
            channel=channel,
            tone=tone,
            link=link,
            message=message
        )
        db.session.add(notification)
        db.session.commit()

        # Теперь собираем письмо
        if self.email_notifications and (email_subject is not None or ini and ini.get(lang, 'email_subject') is not None):
            if email_subject is None:
                email_subject = render_template_string(ini[lang]['email_subject'], **template_context)
            if email_html is None:
                email_tmpl = "{% extends 'mail/base_" + lang.lower() + ".html' %}\n{% block content %}" + ini[lang]['email_html'] + '{% endblock %}'
                email_html = render_template_string(email_tmpl, **template_context)
            if email_text is None:
                if ini[lang].get('email_text'):
                    email_text = render_template_string(ini[lang]['email_text'], **template_context)
                else:
                    email_text = strip_html(email_html)

            send_email(email_subject, [self.email], html_body=email_html, text_body=email_text)

        return notification

    _cache_products = None

    @property
    def products(self):
        if self._cache_products is not None:
            return self._cache_products

        self._cache_products = {}
        for product in UserProduct.query.filter_by(user_id=self.id).all():
            self._cache_products[product.product_id] = product

        return self._cache_products


class UserProduct(db.Model):
    __tablename__ = 'user_products'

    PRODUCTS = ('virtoaster', 'filincam', 'devcon', 'domhub', 'bladerunner')

    user_id = db.Column(db.Integer, db.ForeignKey(User.id, ondelete='CASCADE', onupdate='CASCADE'), primary_key=True)
    product_id = db.Column(db.Enum(*PRODUCTS, name='product'), primary_key=True)

    # Когда юзер приобрёл продукт
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    # Тарифный план продукта. 0 для бесплатных планов.
    plan_id = db.Column(db.SmallInteger(), nullable=False, default=0, server_default='0')
    # Время последнего платежа
    last_payment_time = db.Column(db.DateTime(timezone=True))
    # Время, когда ожидается следующий платёж
    next_payment_time = db.Column(db.DateTime(timezone=True))
    # Произвольные для продукта данные в привязке к юзеру: лимиты, например
    meta = db.Column(JSONB)

    def dict(self):
        return {
            'created': self.created,
            'plan_id': self.plan_id,
            'last_payment_time': self.last_payment_time,
            'next_payment_time': self.next_payment_time,
            'meta': self.meta,
        }


class UserPlanHistory(db.Model):
    """История изменения тарифных планов пользователем"""
    __tablename__ = 'user_plan_history'

    id = db.Column(db.Integer(), primary_key=True)
    product_id = db.Column(db.Enum(*UserProduct.PRODUCTS, name='product'), index=True, nullable=False)
    user_id = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), index=True)
    when = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    plan_id = db.Column(db.Integer(), nullable=False)


class EmailConfirmToken(db.Model):
    __tablename__ = 'email_confirm_tokens'

    @staticmethod
    def gentoken():
        return ''.join([random.choice(string.ascii_letters + string.digits) for _ in range(64)])

    user_id = db.Column(db.Integer, db.ForeignKey(User.id, ondelete='CASCADE', onupdate='CASCADE'), nullable=False, primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    token = db.Column(db.String(80), nullable=False)
    cnt_errors = db.Column(db.Integer, server_default=db.text('0'), default=0, nullable=False)

    user = db.relationship('User', backref=db.backref('email_confirm_tokens', cascade='save-update, merge, delete, delete-orphan'))

    def send(self, templates, subject, recipients):
        send_email(
            template=templates,
            subject=subject,
            recipients=recipients,
            user=self.user,
            token=self.token
        )


class PasswordRecoveryToken(db.Model):
    __tablename__ = 'password_recovery_tokens'

    @staticmethod
    def gentoken():
        return secrets.token_urlsafe(32)

    user_id = db.Column(db.Integer, db.ForeignKey(User.id, ondelete='CASCADE', onupdate='CASCADE'), nullable=False,
                        primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    token = db.Column(db.String(80), nullable=False)
    cnt_errors = db.Column(db.Integer, server_default=db.text('0'), default=0, nullable=False)

    user = db.relationship('User', backref=db.backref('password_recovery_tokens',
                                                      cascade='save-update, merge, delete, delete-orphan'))


class UserAuth(db.Model):
    """OAuth-токены пользователей"""
    __tablename__ = 'user_auth'

    user_id = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'),
                        primary_key=True)
    provider = db.Column(db.Enum('fb', 'vk', 'google', 'yandex', name='auth_provider'), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    remote_id = db.Column(db.String())
    access_token = db.Column(db.String())
    url = db.Column(db.String())  # URL профиля пользователя на внешнем сервисе, если есть


class AuthToken(db.Model):
    __tablename__ = 'auth_tokens'

    id = db.Column(db.Integer(), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id, ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    ip = db.Column(INET(), nullable=False)
    expires = db.Column(db.DateTime(timezone=True), nullable=False)
    signature = db.Column(db.String(128), nullable=False, default='')
    title = db.Column(db.String(), nullable=False, default='')

    user = db.relationship('User',
                           backref=db.backref('auth_tokens', cascade='save-update, merge, delete, delete-orphan'))

    @staticmethod
    def generate(length=None):
        """Генерирует строку, которую можно записать в AuthToken.signature"""
        return secrets.token_urlsafe(length)

    @staticmethod
    def parse_token(token):
        """Парсит токен из формата X|{id}|{signature} и возвращает кортеж (id, signature). В случае ошиюок бросает ValueError."""
        x = token.split('|', 2)
        if len(x) < 3:
            raise ValueError
        if x[0] != 'X':
            raise ValueError
        if not x[1].isnumeric():
            raise ValueError
        return x[1], x[2]

    def __str__(self):
        return 'X|{}|{}'.format(self.id, self.signature)


class Department(db.Model):
    __tablename__ = 'team_departments'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    title = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text())
    boss_id = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'))

    boss = db.relationship('User')


class TeamMember(db.Model, storage.Entity):
    __tablename__ = 'team_members'

    ROLES = OrderedDict([
        ('admin.access', 'Доступ в админку'),
        ('super', 'Суперпользователь, может всё'),
        ('sources.print', 'Распечатывать исходные коды для защиты авторских прав'),
        ('tours', 'Создавать и редактировать туры, фото и презентации'),
        ('estates', 'Создавать и редактировать объекты недвижимости'),
        ('hardware.edit', 'Создавать и редактировать гаджеты '),
        ('users', 'Создавать и редактировать обычных пользователей'),
        ('team', 'Создавать и редактировать членов команды'),
        ('vacancies', 'Создавать и редактировать вакансии'),
        ('texts', 'Редактировать текстовый контент'),
        ('orders', 'Управлять заказами'),
        ('gallery', 'Управлять галереей'),
        ('spam', 'Управлять рассылками'),
        ('br.operator', 'Оператор камеры'),
        ('br.super', 'Менеджер операторов'),
        ('remote-processing', 'Удалённая система'),
        ('remote-processing.view', 'Смотреть на удалённые системы'),
    ])

    user_id = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True)
    roles = db.Column(ARRAY(db.String(32), zero_indexes=True))
    telegram = db.Column(db.String(32), nullable=True)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id'))
    office_days = db.Column(db.Integer(), server_default='5', nullable=False)
    _timezone = db.Column(db.String(25), nullable=True)

    # Дата приёма на работу
    hired = db.Column(db.Date())
    # Дата увольнения
    fired = db.Column(db.Date())

    department_id = db.Column(db.Integer(),
                              db.ForeignKey('team_departments.id', ondelete='RESTRICT', onupdate='CASCADE'))
    position = db.Column(db.String(256), nullable=False, default='')

    description = db.Column(db.Text)
    phone_mobile = db.Column(db.String(128))
    phone_internal = db.Column(db.String(128))
    birthdate = db.Column(db.Date())
    location_url = db.Column(db.String(1024))

    avatar = ImageAsset(width=200, height=200, transform='crop')
    photo = ImageAsset(width=1024, height=1024, transform='fit')

    user = db.relationship('User', back_populates='team_member')
    city = db.relationship('City', back_populates='team_member')
    department = db.relation('Department')

    @property
    def entity_id(self):
        return self.user_id

    def can_edit(self):
        """Может ли current_user редактировать этого сотрудника?
        А могут это делать суперпользователи и руководители отделов."""
        if not current_user.is_authenticated or not current_user.team_member:
            return False

        if current_user.has_role('team'):
            return True

        if self.department_id and self.department.boss_id == current_user.id:
            return True

        return False

    def till_birthday(self):
        """Возвращает количество дней до дня рождения, и None если дата рождения не указана."""
        if not self.birthdate:
            return None
        today = date.today()
        return (self.birthdate.replace(year=today.year) - today).days

    @property
    def timezone(self):
        return self._timezone

    @timezone.setter
    def timezone(self, value):
        if value in current_app.config['TIMEZONES']:
            self._timezone = value
        else:
            self._timezone = None


class TeamMemberStatus(db.Model):
    """Информация об отпусках и больничных"""
    __tablename__ = 'team_statuses'

    TEAM_STATUSES = OrderedDict(
        [('vacation', 'отпуск'),
         ('sick-leave', 'больничный'),
         ('maternity-leave', 'декретный'),
         ('business-trip', 'командировка'),
         ('other', 'прочие')]
    )

    id = db.Column(db.Integer(), primary_key=True)
    user_id = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'))
    type = db.Column(
        db.Enum('other', 'vacation', 'sick-leave', 'maternity-leave', 'business-trip', name='team_member_status_type'),
        nullable=False, server_default='other')
    start = db.Column(db.Date, nullable=False)
    finish = db.Column(db.Date, nullable=True)
    comment = db.Column(db.Text)
    user = db.relationship('User', back_populates='team_status')

    def type_name(self):
        return self.TEAM_STATUSES.get(self.type, '???')


class TeamMemberPhotoQueue(db.Model, storage.Entity):
    __tablename__ = 'team_member_photo_queue'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id, ondelete='CASCADE', onupdate='CASCADE'), nullable=False)

    photo = ImageAsset(width=1024, height=1024, transform='fit')

    user = db.relationship('User')


class Notification(db.Model):
    __tablename__ = 'notifications'

    TONES = ['error', 'warning', 'success', 'info', 'action']
    CHANNELS = ['virtoaster', 'filincam', 'devcon', 'bladerunner', 'locus', 'billing', 'common', 'spam']

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id, ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    channel = db.Column(db.String(12), nullable=False)
    tone = db.Column(db.Enum(*TONES, name='notification_tone'), nullable=False)
    message = db.Column(db.String(1024), nullable=False)
    link = db.Column(db.String(1024))
    seen = db.Column(db.DateTime(timezone=True))
    clicked = db.Column(db.DateTime(timezone=True))

    def api_repr(self):
        r = {
            'id': self.id,
            'created': self.created.isoformat(),
            'channel': self.channel,
            'tone': self.tone,
            'message': self.message,
            'link': self.link,
            'click_link': url_for('front.notification_click', notification_id=self.id),
            'seen': None if self.seen is None else self.seen.isoformat(),
            'clicked': None if self.clicked is None else self.clicked.isoformat(),
        }

        return r


class Tag(db.Model):
    """Пользовательский тег. Сам тег, без его значения, значения развешиваются в TourTag, EstateTag и т.п."""
    __tablename__ = 'tags'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    label = db.Column(db.String(1024))
    name = db.Column(db.String(64), nullable=False)
    # Если теги синхронизируются с какими-то свойствами из внешней CRM, то тут название этого свойства
    crm_key = db.Column(db.String(255))
    # Словарь преобразований значений. Например: {'1': '1-комнатная', '2': '2-комнатная', '0': 'студия'}
    display_dict = db.Column(JSONB)
    # Префикс, который нужно показывать перед значением, например 'примерно'
    prefix = db.Column(db.String(255))
    # Суффикс, который нужно показывать после значения, например 'кв. м.'
    suffix = db.Column(db.String(255))

    def __repr__(self):
        return f'<Tag #{self.id}@{self.user_id} "{self.name}">'

    def api_repr(self, **kwargs):
        r = {
            **{
                'id': self.id,
                'created': self.created.isoformat(),
                'user_id': self.user_id,
                'name': self.name,
                'label': self.label,
                'crm_key': self.crm_key,
                'display_dict': self.display_dict,
                'prefix': self.prefix,
                'suffix': self.suffix,
            },
            **kwargs
        }
        return r

    def format(self, val):
        if val is None:
            return None
        if self.display_dict:
            val = self.display_dict.get(val, val)
        return (self.prefix or '') + val + (self.suffix or '')

    def update_from_api_request(self, payload):
        """
        Обновляет свои свойства из тела запроса API в `payload`. Проверяет их на валидность и выбрасывает
        abort(400).
        :param payload: dict {name, crm_key, display_dict, prefix, suffix}
        :return:
        """
        if 'name' in payload:
            if type(payload['name']) is not str:
                abort(400, gettext('Malformed %(key)s value.', key='name'))

            name = payload['name'].strip()
            if name == '':
                abort(400, gettext(gettext('Tag name should not be empty')))

            # Проверяем уникальность имени
            q = Tag.query.filter_by(user_id=current_user.id, name=name)
            if self.id:
                q = q.filter(Tag.id != self.id)
            if q.first():
                abort(400, gettext('Tag "%(name)s" already exists.', name=name))

            self.name = name

        if 'label' in payload:
            if payload['label'] is None:
                self.label = None
            else:
                self.label = str(payload['label'])

        if 'crm_key' in payload:
            if payload['crm_key'] is None:
                self.crm_key = None
            else:
                self.crm_key = str(payload['crm_key'])

        if 'display_dict' in payload:
            if payload['display_dict'] is not None and type(payload['display_dict']) is not dict:
                abort(400, gettext('Malformed %(key)s value.', key='display_dict'))

            self.display_dict = payload['display_dict']

        if 'prefix' in payload:
            if payload['prefix'] is None:
                self.prefix = None
            else:
                self.prefix = str(payload['prefix'])

        if 'suffix' in payload:
            if payload['suffix'] is None:
                self.suffix = None
            else:
                self.suffix = str(payload['suffix'])

