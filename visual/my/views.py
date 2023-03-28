import logging
import traceback
from collections import OrderedDict
import json
from datetime import datetime

from flask import render_template, abort, request, flash, redirect, url_for, jsonify, current_app, Response, g
from flask_login import current_user, login_required
from flask_babel import gettext
import stripe

from . import mod
from ..models import User, Tour, Footage, AggregateCount, Folder, DCProject, DCMembership
from ..core import db

log_billing = logging.getLogger('billing')


@mod.route('/')
@mod.route('/<path:path>')
def index(path=None):
    return render_template('my/index.html', path=path, timezones=current_app.config['TIMEZONES'])


@mod.route('/devcon/<project_id>')
@mod.route('/devcon/<project_id>/<path:path>')
@login_required
def devcon(project_id, path=None):

    project = DCProject.query.filter_by(id=project_id).first()
    if not project:
        abort(404, description=gettext('Project not found.'))

    membership = DCMembership.query.filter_by(project_id=project_id, user_id=current_user.id).first()

    if not "devcon" in current_user.products:
        abort(403, '@not-a-project-member')

    return render_template('my/devcon.html', path=path)


@mod.route('/orders/')
@mod.route('/orders/<path:path>')
@mod.route('/br/<path:path>')
@login_required
def bladerunner(path=None):

    if not "bladerunner" in current_user.products:
        abort(403, '@not-a-project-member')

    return render_template('my/bladerunner.html', path=path)


@mod.route('/settings/payment/complete/')
@login_required
def settings_payment_complete():
    print('settings_payment_complete(): ', request.args.get('session_id'), request.url)

    """Сюда Stripe редиректит после того, как юзер ввёл на checkout.stripe.com новые платёжные реквизиты."""
    if not request.args.get('session_id'):
        return redirect(url_for('my.index', path='settings/payment/'))

    try:
        log_billing.debug('Юзер поменял реквизиты на checkout.stripe.com, обрабатываем сессию')
        # 1. Получаем setup-сессиию
        session = stripe.checkout.Session.retrieve(request.args['session_id'], expand=['setup_intent'])
        log_billing.debug('checkout.Session: ' + str(session))

        # 2. Аттачим Payment Method к Customer
        stripe.PaymentMethod.attach(
            session.setup_intent.payment_method,
            customer=session.setup_intent.metadata.customer_id
        )

        # 3. Делаем этот Payment Method дефолтным для кастомера
        stripe.Customer.modify(
            session.setup_intent.metadata.customer_id,
            invoice_settings={'default_payment_method': session.setup_intent.payment_method}
        )

        log_billing.info('Клиенту {} назначен PaymentMethod {}'.format(session.setup_intent.metadata.customer_id, session.setup_intent.payment_method))
    except Exception as e:
        log_billing.error('Ошибка при обработке смены платёжного метода сессии {}'.format(request.args['session_id']))
        log_billing.error(traceback.format_exc())
        flash(gettext('Payment gateway error. Please try again later.'), 'danger')
        return redirect(url_for('my.index', path='settings'))

    flash(gettext('Payment details have been updated.'), 'success')
    return redirect(url_for('my.index', path='settings'))


@mod.route('/settings/payment/')
@login_required
def settings_payment():
    """
    Изменение платёжных реквизитов. Создаёт Stripe-сессию и рендерит шаблон, который редиректит на страницу
    на checkout.stripe.com для ввода новых данных.
    :return:
    """
    customer = current_user.stripe_get_customer()
    if customer is None:
        flash('You do not have any billing details.')
        return redirect(url_for('my.index', path='settings'))

    if len(customer.subscriptions.data) == 0:
        flash('You do not have active subscriptions.')
        return redirect(url_for('my.index', path='settings'))

    subscription = customer.subscriptions.data[0]

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        mode='setup',
        setup_intent_data={
            'metadata': {
                'customer_id': current_user.stripe_customer_id,
                'subscription_id': subscription.id,
            },
        },
        billing_address_collection='required',
        success_url=url_for('my.settings_payment_complete', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=url_for('my.index', path='settings', _external=True),
    )

    print('Success url:', url_for('my.settings_payment_complete', _external=True) + '?session_id={CHECKOUT_SESSION_ID}')

    return render_template('my/settings_payment_redirect.html', session=session)


@mod.route('/settings/promocode/', methods=('GET', 'POST'))
@login_required
def settings_promocode():
    """
    Обновляет подписку с учетом промокода.
    :return:
    """
    promo_code = None
    promo_code_id = None

    if request.json.get('promo_code'):
        promo_code = request.json.get('promo_code')

    customer = current_user.stripe_get_customer()

    if customer and len(customer.subscriptions.data) == 1:
        subscription = customer.subscriptions.data[0]
    else:
        return jsonify({'result': {'danger': gettext('You do not have active subscriptions.')}})

    if promo_code:
        promo_codes = stripe.PromotionCode.list(active=True, limit=100)
        for promo_code_obj in promo_codes['data']:
            if promo_code == promo_code_obj.get('code', None):
                if promo_code_obj.get('coupon', {}).get('metadata',{}).get('applicable_product', None) == 'subscription':
                    promo_code_id = promo_code_obj['id']
    try:
        if promo_code_id:
            stripe.Subscription.modify(
                subscription.id,
                promotion_code=promo_code_id
            )
    except stripe.error.InvalidRequestError as e:
        log_billing.error("Ошибка при обновлении промокода для подписки: {}".format(str(e)))
        return jsonify({'result': {'danger': gettext('There was a problem with billing service, please try again later.')}})

    result = {'result': {'success': gettext('Promo code successfully redeemed!')}} if promo_code_id \
        else {'result': {'danger': gettext('Promo code can not be redeemed!')}}

    return jsonify(result)
