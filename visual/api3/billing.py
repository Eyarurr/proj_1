import json
import requests

from urllib.parse import urljoin
from requests.exceptions import ReadTimeout, ConnectionError

from flask import request, abort, current_app, url_for
from flask_login import current_user, login_required
from flask_babel import gettext
import stripe

from . import mod, api_response
from visual.core import db
from visual.models import Tour, TourPaidFeature


@mod.route('/billing/paid-features', methods=('POST', ))
@login_required
def post_billing_paid_features():
    """
    POST /billing/paid-features
    Купить платные фичи
    Input:
    {
        tour_id: {feature: amount, ...},
        ...
    }
    Response:
    {
        "status": "success" | "fail"
        "price": float,  // для status=success
        "message": str,  // для status=fail
    }
    """
    result = {}

    # Платные фичи не могут покупать триальные юзеры
    if 'virtoaster' in current_user.products and current_user.products['virtoaster'].plan_id == 0:
        abort(400, gettext(
            'You can not buy tour features while on Trial plan. Please <a href="%(url)s">upgrade your account</a>.',
            url=url_for('virtoaster.pricing')
        ))

    # У юзера должен быть Stripe Customer. Он, по идее, есть у всех не-триальных юзеров, поэтому если эта проверка сработала,
    # значит действительно случилась какая-то хуйня.
    if not current_user.stripe_customer_id:
        abort(400, gettext(
            'Your billing details are invalid. Please update your credit card information on the <a href="%(url)s">Settings page</a>.',
            url=url_for('my.index', path='settings')
        ))

    total_price = 0
    order = []
    promo_code = None
    coupon_id = None
    # Строим данные для будущих InvoiceItem
    for tour_id, features in request.json.items():
        promo_code = features.pop('promo_code', None)

        tour = Tour.query.options(db.joinedload(Tour.paid_features_rel)).get(tour_id)
        if not tour:
            abort(404, gettext('Tour %(tour_id)s not found.', tour_id=tour_id))
        if tour.user_id != current_user.id:
            abort(403, gettext('Tour %(tour_id)s does not belong to you.', tour_id=tour.id))

        for feature, quantity in features.items():
            if feature not in current_app.config['PAID_FEATURES']:
                abort(400, gettext('Unknown feature %(feature)s.', feature=feature))

            PFCONFIG = current_app.config['PAID_FEATURES'][feature]

            # Может ли юзер купить эту фичу на своём тарифном плане
            if 'not_available_at_plans' in PFCONFIG and current_user.products['virtoaster'].plan_id in PFCONFIG['not_available_at_plans']:
                abort(400, gettext(
                    'You can not buy feature "%(feature)s" on your plan. Please <a href="%(url)s">upgrade your account</a>.',
                    feature=feature, url=url_for('virtoaster.pricing')
                ))

            total_price += PFCONFIG['price'] * quantity

            order.append({
                'price': PFCONFIG['stripe_price_id'],
                'quantity': quantity,
                'description': '{} for tour #{}'.format(PFCONFIG['description'], tour.id),
                'metadata': {
                    'what': 'paid-feature',
                    'tour_id': tour.id,
                    'feature': feature
                }
            })

    if not order:
        abort(400, gettext('Nothing to purchase.'))

    try:
        if promo_code:
            promo_codes = stripe.PromotionCode.list(active=True, limit=100)
            for promo_code_obj in promo_codes['data']:
                if promo_code == promo_code_obj.get('code', None):
                    if promo_code_obj.get('coupon', {}).get('metadata', {}).get('applicable_product', None) == 'branding':
                        coupon_id = promo_code_obj['coupon']['id']
        if promo_code and coupon_id is None:
            abort(400, gettext('Promo code can not be redeemed!'))

        for item in order:
            stripe.InvoiceItem.create(
                customer=current_user.stripe_customer_id,
                **item
            )

        params={
            'customer': current_user.stripe_customer_id,
            'automatic_tax': {"enabled": True}
        }
        if coupon_id:
            params['discounts']=[{'coupon': coupon_id}]
        invoice = stripe.Invoice.create(**params)
    except stripe.error.InvalidRequestError as e:
        abort(400, gettext('Billing error: %(error)s.', error=str(e)))

    msg_card_fail = gettext(
        'Failed charging your credit card. Please update your credit card information on the <a href="%(url)s">Settings page</a>.',
        url=url_for('my.index', path='settings')
    )

    try:
        invoice = stripe.Invoice.pay(invoice.id)
    except stripe.error.CardError as e:
        abort(400, msg_card_fail)
    except stripe.error.InvalidRequestError as e:
        abort(400, gettext('Billing error: %(error)s.', error=str(e)))

    if invoice.status == 'paid':
        return api_response({
            'status': 'success',
            'price': total_price
        })
    else:
        if invoice.status == 'draft':
            stripe.Invoice.delete(invoice.id)
        else:
            stripe.Invoice.void(invoice.id)
        abort(400, msg_card_fail)

    return api_response(result)
