import json
import random

from flask import render_template, redirect, request, url_for, flash, make_response, current_app
from flask_login import login_user, current_user
from sqlalchemy.exc import IntegrityError
import stripe

from visual.core import db, products
from visual.util import flash_errors
from visual.models import User, Folder, Tour, Offer, UserPlanHistory, UserProduct

from .. import mod, roles_required
from .forms import EditUserForm, NewUserForm, UserFiltersForm, EditProductForm, AddProductForm


@mod.route('/users/')
def users():
    filters = UserFiltersForm(request.args)

    # Добавляем подзапрос для подсчёта количества мультимедии в объектах
    tour_count = db.session.query(Tour.user_id, db.func.count(Tour.id).label('cnt_tours')).group_by(Tour.user_id).subquery()
    mt_count = db.session.query(Folder.user_id, db.func.count(Offer.id).label('cnt_multitours')).join(Folder).group_by(Folder.user_id).subquery()

    query = db.session\
        .query(
            User,
            db.func.json_object_agg(db.func.coalesce(db.func.cast(UserProduct.product_id, db.Text), '*'), UserProduct.plan_id),
            tour_count.c.cnt_tours,
            mt_count.c.cnt_multitours
        ) \
        .outerjoin(UserProduct) \
        .outerjoin(tour_count, User.id == tour_count.c.user_id) \
        .outerjoin(mt_count, User.id == mt_count.c.user_id) \
        .group_by(User.id, tour_count.c.cnt_tours, mt_count.c.cnt_multitours)

    # Поиск
    if filters.search.data:
        like = '%' + filters.search.data.lower() + '%'
        query = query.filter(
            db.or_(
                db.func.lower(User.name).like(like),
                db.func.lower(User.email).like(like)
            )
        )

    # Только с платными продуктами
    if filters.paid.data:
        query = query.join(db.aliased(UserProduct)).filter(UserProduct.plan_id != 0)

    # Сортировка
    sorts = {
        'name': [User.name],
        'cnt_tours': [tour_count.c.cnt_tours.desc().nullslast()],
        'last_active': [User.last_active.desc().nullslast(), User.name]
    }
    query = query.order_by(*sorts.get(filters.sort.data, [User.created.desc(), User.name]))

    users = query.paginate(per_page=50, error_out=False)

    return render_template('admin/users/index.html', users=users, filters=filters)


@mod.route('/users/new/', methods=['GET', 'POST'])
@mod.route('/users/<int:user_id>/edit/', methods=['GET', 'POST'])
@roles_required('users')
def user_edit(user_id=None):
    if user_id:
        user = User.query.get_or_404(user_id)

        form = EditUserForm(obj=user)
    else:
        user = User(created_by=current_user.id)
        form = NewUserForm(obj=user)

    if request.method == 'POST':
        if form.validate_on_submit():
            email_namesake = User.query\
                .filter(db.func.lower(User.email) == form.email.data.lower(), User.id != user.id)\
                .first()
            if email_namesake:
                flash(
                    'Пользователь с таким адресом электронной почты уже существует (<a href="%s">%s</a>).' %
                    (url_for('.user_edit', user_id=email_namesake.id), email_namesake.name),
                    'danger'
                )
            else:
                if form.avatar_delete.data:
                    del user.avatar

                form.populate_obj(user)
                db.session.add(user)
                db.session.flush()

                if form.avatar_.data:
                    user.avatar = form.avatar_.data

                if form.contacts.data:
                    user.contacts = json.loads(form.contacts.data)
                else:
                    user.contacts = {}

                if form.password.data != '':
                    user.password_hash = User.hash_password(form.password.data)

                user.timezone = request.form.get('timezone')

                db.session.commit()

                return redirect(url_for('.users'))
        else:
            flash_errors(form)
    else:
        form.contacts.data = json.dumps(user.contacts, ensure_ascii=False)
        if not user.id:
            form.password.data = ''.join([random.choice('abvgdezkmnoprstufhz23456789') for _ in range(8)])

    return render_template('admin/users/edit.html', user=user, form=form, timezones=current_app.config['TIMEZONES'])


@mod.route('/users/<int:user_id>/delete/', methods=['POST'])
@roles_required('users')
def user_delete(user_id):
    user = User.query.get_or_404(user_id)

    try:
        db.session.delete(user)
        db.session.commit()
        flash('Пользователь {} удалён.'.format(user.email), 'success')
    except IntegrityError as e:
        flash('Удалить пользователя не удалось, так как у него есть привязанные объекты (туры или ещё чего).', 'danger')

    return redirect(url_for('.users'))


@mod.route('/users/<int:user_id>/products/')
def user_products(user_id):
    user = User.query.get_or_404(user_id)

    form_add_product = AddProductForm()
    form_add_product.product_id.choices = [(k, k) for k in UserProduct.PRODUCTS]

    return render_template('/admin/users/products.html', user=user, form_add_product=form_add_product)


@mod.route('/users/<int:user_id>/products/new/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/products/<product_id>/edit/', methods=('GET', 'POST'))
def user_product_edit(user_id, product_id=None):
    user = User.query.get_or_404(user_id)

    if product_id is None:
        # Добавляем продукт юзеру
        product_id = request.args.get('product_id')
        if product_id not in UserProduct.PRODUCTS:
            flash(f'Нет такого продукта: "{product_id}"', 'danger')
            return redirect(url_for('.user_products', user_id=user.id))
        if product_id in user.products:
            flash(f'У юзера уже есть продукт "{product_id}"', 'info')
            return redirect(url_for('.user_product_edit', user_id=user.id, product_id=product_id))
        product = UserProduct(user_id=user.id, product_id=product_id, plan_id=0)
        is_new = True
    else:
        product = UserProduct.query.get_or_404((user_id, product_id))
        is_new = False

    form = EditProductForm(obj=product)
    form.plan_id.choices = [
        (k, v.title)
        for k, v in products[product.product_id].plans.items()
    ]

    if form.validate_on_submit():
        form.populate_obj(product)
        try:
            product.meta = json.loads(form.meta_str.data)
        except json.decoder.JSONDecodeError as e:
            form.meta_str.errors = [f'Ошибка JSON: {e}']
        else:
            db.session.add(product)
            db.session.commit()
            return redirect(url_for('.user_products', user_id=user.id))
    else:
        form.meta_str.data = json.dumps(product.meta, indent=4, ensure_ascii=False, sort_keys=True)

    return render_template('/admin/users/product_edit.html', user=user, product=product, form=form, is_new=is_new)


@mod.route('/users/<int:user_id>/products/<product_id>/delete/', methods=('POST', ))
def user_product_delete(user_id, product_id=None):
    product = UserProduct.query.get_or_404((user_id, product_id))

    db.session.delete(product)
    db.session.commit()

    return redirect(url_for('.user_products', user_id=product.user_id))


@mod.route('/users/<int:user_id>/billing/')
def user_billing(user_id):
    user = User.query.get_or_404(user_id)

    stripe_error = None
    customer = {}
    payment_methods = []

    if user.stripe_customer_id:
        try:
            customer = user.stripe_get_customer()
            payment_methods = stripe.PaymentMethod.list(
                customer=user.stripe_customer_id,
                type="card",
            )
        except Exception as e:
            stripe_error = str(e)

    return render_template('admin/users/billing.html', user=user, customer=customer, payment_methods=payment_methods, stripe_error=stripe_error)


@mod.route('/users/<int:user_id>/products/history')
def user_products_history(user_id):
    user = User.query.get_or_404(user_id)
    products_history = UserPlanHistory.query.filter_by(user_id=user.id).order_by(UserPlanHistory.when.desc()).all()

    return render_template('admin/users/products_history.html', user=user, products_history=products_history)


@mod.route('/users.json')
@mod.route('/misc/users/')
def users_json():
    users = [
        {'id': u.id, 'name': u.name, 'email': u.email}
        for u in User.query.order_by(User.name).all()
    ]
    response = make_response(json.dumps(users, ensure_ascii=False))
    response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
    return response


@mod.route('/users/authas/', methods=('POST',))
@roles_required('users')
def user_authas():
    user = User.query.get_or_404(request.form.get('user_id'))
    login_user(user)
    return redirect(url_for('my.index'))
