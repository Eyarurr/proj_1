import logging
import datetime
import typing
from email_validator import validate_email, EmailNotValidError
from flask import request, abort, current_app, g
from flask_login import current_user, login_required, login_user
from flask_babel import gettext
import stripe
from pydantic import BaseModel, Extra, ValidationError

from . import mod, api_response
from visual.core import db
from visual.models import User, AuthToken
from .common import load_user_edit, handle_asset_param
from visual.mail import send_email


def expand_fields(fields_param):
    fields = set(fields_param.split(','))
    if 'default' in fields:
        fields.remove('default')
        fields.update(['id', 'name', 'settings'])

    return fields


@mod.route('/my')
@login_required
def get_me():
    """
    GET /me
    """
    fields = request.args.get('fields', '').split(',')

    warnings = []
    add = {}
    for k in ('last_active', 'stripe_customer_id'):
        if k in fields:
            add[k] = getattr(current_user, k)

    if 'octobat_customer' in fields:
        val = current_user.octobat_get_cusomer()
        if val and 'errors' in val:
            warnings.append(gettext('Billing error: Octobat HTTP request API error: %(error)s.', error=val.get("message")))
        add['octobat_customer'] = val

    if 'count_footages' in fields:
        add['count_footages'] = current_user.count_footages()

    if 'purge_timedelta' in fields:
        ptd = current_user.purge_timedelta()
        if ptd is not None:
            ptd = ptd.days
        add['purge_timedelta'] = ptd

    if 'notifications_unseen' in fields:
        add['notifications_unseen'] = current_user.notifications_unseen()

    result = current_user.current_user_api_repr(_settings_no_default=request.args.get('settings') == 'nodefault', **add)

    return api_response(result, warnings=warnings)


@mod.route('/users/<int:user_id>')
@login_required
def get_user(user_id):
    """
    GET /users/<user_id>
    Отдаёт данные о юзере
    """
    user = User.query.get_or_404(user_id, description=gettext('User not found.'))

    if user.id != current_user.id:
        abort(403, gettext('You can not view other user\'s data.'))

    return api_response(user.api_repr())


class UserContactInput(BaseModel, extra=Extra.forbid):
    sort: int = None
    type: str
    value: str
    note: str = None
    visible: typing.List[str] = None


@mod.route('/my', methods=('PUT', ))
@mod.route('/users/<int:user_id>', methods=('PUT', ))
@login_required
def put_user(user_id=None):
    """
    PUT /users/<user_id>
    Input:
    {
        "email": str,
        "name": str,
        "password": {
            "old": str,
            "new": str
        }
        "timezone": str,
        "email_notifications": int
        "settings": dict
        "avatar": AssetString
        "contacts": {id: UserContact, ...}
    }
    """
    if user_id is None:
        user = current_user
    else:
        user = load_user_edit(user_id)

    simple_props = {'name': str, 'email_notifications': int}
    warnings = []
    for key, value in request.json.items():
        if key in simple_props:
            try:
                setattr(user, key, simple_props[key](value))
            except ValueError:
                abort(400, gettext('Bad data type for property %(property)s', property=key))
        elif key == 'email':
            try:
                value = str(value).strip().lower()
            except ValueError:
                abort(400, gettext('Bad data type for property %(property)s', property='email'))

            try:
                validate_email(value)
            except EmailNotValidError as e:
                abort(400, gettext('The email address is not valid.'))
            existing = User.query.filter(db.func.lower(User.email) == value, User.id != user.id).first()
            if existing:
                abort(400, gettext('Email %(email)s already registered for another user.', email=value))
            user.email = value
        elif key == 'timezone':
            if value not in current_app.config['TIMEZONES']:
                abort(400, gettext('Unknown timezone "%(timezone)s"', timezone=value))
            user.timezone = value
        elif key == 'password':
            if len(value['new']) < 6:
                abort(400, gettext("Password should contain at least six symbols."))
            if User.hash_password(value['old']) != current_user.password_hash:
                abort(400, 'Old password is not correct.')
            current_user.password_hash = User.hash_password(value['new'])
        elif key == 'settings':
            try:
                user.settings_obj.merge(value)
            except ValueError as e:
                abort(400, str(e))
            user.settings_save()
            db.session.commit()
        elif key == 'avatar':
            if value is None:
                del user.avatar
            else:
                with handle_asset_param(value, 'avatar') as (fh, *_):
                    user.avatar = fh
        elif key == 'contacts':
            if value is None:
                user.contacts = None
            else:
                if type(value) is not dict:
                    abort(400, 'API: "contacts" should be object or null')
                user.contacts = {}
                for k, v in value.items():
                    try:
                        c = UserContactInput(**v)
                    except ValidationError as e:
                        return abort(400, f'API: bad input: {e}')
                    user.contacts[k] = c.dict(exclude_defaults=True)
        else:
            warnings.append(gettext('Unknown input property %(property)s', property=key))

    db.session.commit()

    return api_response(user.api_repr(), warnings=warnings)


@mod.route('/my/delete', methods=('POST', ))
@mod.route('/users/<int:user_id>/delete', methods=('POST', ))
def user_delete(user_id=None):
    """
    POST /users/<user_id>/delete
    Input:
        { "password": str }
    """
    user = load_user_edit(user_id)

    if user.deleted:
        abort(400, gettext('Your account is already marked for deletion.'))

    if user.password_hash != User.hash_password(request.json.get('password')):
        abort(400, gettext('Password is not correct!'))

    # Если у юзера есть Stripe Customer, то находим его подписки и удаляем их
    log_billing = logging.getLogger('billing')
    if user.stripe_customer_id:
        try:
            customer = stripe.Customer.retrieve(user.stripe_customer_id)
        except stripe.error.InvalidRequestError as e:
            log_billing.error('Удаление юзера {u.email} (u.stripe_customer_id): не удалось получить Customer из Stripe'.format(str(e), u=user), exc_info=True)
        else:
            for subscription in customer.subscriptions.data:
                log_billing.debug('Удаление юзера {u.email} (u.stripe_customer_id): удаляем подписку {s.id}'.format(u=user, s=subscription))
                try:
                    stripe.Subscription.delete(subscription.id)
                except stripe.error.InvalidRequestError as e:
                    log_billing.error('Удаление юзера {u.email} (u.stripe_customer_id): ошибка при удалении подписки {s.id}: {}'.format(
                        str(e), s=subscription, u=user, c=customer
                    ))

    user.set_virtoaster_plan(0)
    user.deleted = db.func.now()
    db.session.commit()

    return '', 204


@mod.route('/my/undelete', methods=('POST', ))
@mod.route('/users/<int:user_id>/undelete', methods=('POST', ))
def user_undelete(user_id=None):
    """
    POST /users/<user_id>/undelete
    """
    user = load_user_edit(user_id)

    if user.deleted is None:
        abort(400, 'User is not marked for deletion.')

    user.deleted = None
    db.session.commit()

    return '', 204


@mod.route('/users/login', methods=('POST', ))
def user_login():
    if type(request.json) is not dict or 'email' not in request.json or 'password' not in request.json:
        abort(400, 'Malformed input data.')
    if type(request.json['email']) is not str or type(request.json['password']) is not str:
        abort(400, 'Malformed input data.')

    user = User.query.filter(db.func.lower(User.email) == request.json.get('email', '').lower().strip()).first()
    if not user:
        abort(403, gettext('Wrong login.'))

    if User.hash_password(request.json.get('password', '')) != user.password_hash:
        return abort(403, gettext('Wrong password.'))

    if not user.email_confirmed:
        return abort(403, gettext("Please check your inbox for an email with your account activation link."))
    if user.banned:
        return abort(403, gettext("The password is correct, but your personal account is not active."))
    if user.deleted:
        return abort(403, gettext("The password is correct, but your personal account is deleted."))

    login_user(user)
    user_dict = user.current_user_api_repr()

    # Пока жоска зашьём метод генерации токена, на случай, если где-нибудь понадобится создавать клиентские токены
    method = 'server_session'

    if method == 'server_session':
        # Токен для серверной сессии
        try:
            expires = request.json.get('expires')
            if expires:
                expires = datetime.datetime.fromisoformat(expires)
                if expires < datetime.datetime.now():
                    abort(400, 'Requested token expiration time is in past.')
            else:
                expires = datetime.datetime.now() + datetime.timedelta(days=30)
        except ValueError:
            abort(400, 'Malformed expires value.')
            return

        title = request.json.get('title')
        if title is None:
            title = request.headers.get('User-Agent')
        if not title:
            title = '{} {}'.format(g.api_client, g.api_client_version)
        try:
            title = str(title)
        except ValueError:
            abort(400, 'Malformed title value.')
        ip = request.remote_addr if getattr(request, 'remote_addr', None) else '127.0.0.1'
        token = AuthToken(ip=ip, user_id=user.id, expires=expires, signature=AuthToken.generate(), title=title)
        db.session.add(token)
        db.session.commit()

        result = {
            'token': str(token),
            'expires': datetime.datetime.isoformat(token.expires),
            'title': title,
            'user': user_dict
        }
    else:
        # Токен для клиентской сессии, использовался до октября 2020-го
        result = {
            'token': user.get_api_auth_token(),
            'user': user_dict
        }

    return api_response(result)


@mod.route('/users/logout', methods=('POST', ))
@login_required
def user_logout():
    token = request.args.get('auth_token')
    try:
        token_id, signature = AuthToken.parse_token(token)
    except ValueError:
        abort('Bad auth_token.')

    AuthToken.query.filter_by(id=token_id).delete()
    db.session.commit()

    return '', 204
