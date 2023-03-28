import datetime
import stripe

from visual import create_app
from visual.core import db, products
from visual.models import User, AuthToken, Tour, Footage, UserProduct

payment_ = {}
subs_ = {}
USERS = {}
TOURS = {}

# Каким юзерам добавили продукт virtoaster
PLAN_IDS = {1: 100, 2: 10, 3: 10, 4: 30, }


def setup_module():
    """
    Добавим четырех обычных пользователей.
    anna@biganto.com - добавим 'plan_id': 100
    boris@biganto.com - добавим stripe_customer_id, в stripe добавим stripe.PaymentMethod, добавим stripe.Subscription = Trial, добавлен plan_id=0
    sidor@biganto.com - добавим stripe_customer_id, в stripe добавим stripe.PaymentMethod, добавим stripe.Subscription = Basic, добавлен plan_id=10
    super@biganto.com - добавим stripe_customer_id, в stripe добавим stripe.PaymentMethod, добавим stripe.Subscription = Business, добавлен plan_id=30
    Ко всем stripe_customer_id добавим stripe.PaymentMethod,
    Ко всем stripe_customer_id добавим stripe.PaymentMethod
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        users = [
            {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com'},
            {'id': 2, 'name': 'boris', 'email': 'boris@biganto.com', 'stripe_customer_id': 'cus_MJdvfyi2idDvUC'},
            {'id': 3, 'name': 'sidor', 'email': 'sidor@biganto.com', 'stripe_customer_id': 'cus_MJdvfXvB9RMIPt'},
            {'id': 4, 'name': 'super', 'email': 'super@biganto.com', 'stripe_customer_id': 'cus_MJdvWgyV2dgzip'},
        ]
        for kwargs in users:
            user = User(email_confirmed=True, **kwargs)
            user.auth_tokens.append(
                AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30),
                          ip='0.0.0.0'))
            db.session.add(user)
            db.session.flush()
            tour = Tour(id=user.id, user_id=user.id, title='tour',
                        footage=Footage(user_id=user.id, _status='testing', type='real'))
            db.session.add(tour)
        db.session.flush()

        # Добавим PaymentMethod, привяжем к customer и добавим подписок
        users = User.query.filter(User.stripe_customer_id != None).all()
        for user in users:
            customer = stripe.Customer.retrieve(user.stripe_customer_id)
            param_pay = {'type': "card",
                         'card': {"number": "4242424242424242", "exp_month": 5, "exp_year": 2023, "cvc": "314",
                                  },
                         'billing_details': {
                             "address": {"city": "", "country": "US", "line1": "", "line2": "", "postal_code": "5555",
                                         "state": ""
                                         }, "email": user.email, "name": user.name}
                         }

            p_method = stripe.PaymentMethod.create(**param_pay)
            stripe.PaymentMethod.attach(p_method.id, customer=customer.id)
            stripe.Customer.modify(customer.id, invoice_settings={'default_payment_method': p_method.id})
            payment_.update({customer.id: customer.invoice_settings.default_payment_method})

            # Добавим подписки:
            # sidor - Basic, super - Business
            if user.id in PLAN_IDS:
                plan_id = PLAN_IDS[user.id]
                sub_id = products.virtoaster.plans[plan_id].processor_id
                params = {'customer': customer.id, 'items': [{'plan': sub_id}]}
                sub = stripe.Subscription.create(**params)
                subs_.update({user.stripe_customer_id: sub.id})
                user.set_virtoaster_plan(plan_id)

            USERS[user.id] = {k: getattr(user, k) for k in ("id", 'email', 'name', 'banned', 'deleted', 'stripe_customer_id')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ("id", 'user_id', 'title')}
        db.session.commit()


def teardown_module():
    """
    После выполнения из stripe удаляем PaymentMethod и Subscription
    """
    for key, val in payment_.items():
        stripe.PaymentMethod.detach(val)
#
    for key, val in subs_.items():
        stripe.Subscription.delete(val)

def test_payment_feature(api):
    """
    Купить платную фичу
    POST /billing/paid-features
    {
    tour_id: {
        feature: years,
        ...
    },

    """
    for user_id, user in USERS.items():
        tour_id = user_id
        params = {'body': {f'{tour_id}': {'branding': 1}}, 'auth_as': user['email']}

        # Пытаемся купить платную фичу.
        # Ожидаемый результат: Только юзер, у которого в stripe куплена подписка Business и выше и user.plain_id >= 30
        # может купить платную фичу
        resp = api.post('/billing/paid-features', **params, _debug=True)
        if PLAN_IDS[user_id] >= 30 and user['stripe_customer_id']:
            assert resp.status_code == 200
            assert resp.result['status'] == 'success'
        else:
            assert resp.status_code == 400
            if user['id'] == 1 or 2:
                resp.has_error('Your billing details are invalid. Please update your credit card information')
            if user['id'] == 3:
                assert resp.has_error('You can not buy feature \"branding\" on your plan')
