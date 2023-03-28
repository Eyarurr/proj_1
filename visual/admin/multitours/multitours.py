import json
from datetime import datetime, timedelta

from flask import render_template, redirect, url_for, request, jsonify, flash, abort
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, FileField, SelectField, HiddenField,\
    ValidationError, TextAreaField, IntegerField, BooleanField, DateTimeField
from flask_login import current_user
from sqlalchemy.orm.attributes import flag_modified

from visual.core import db
from visual.models import Folder, Tour, Offer, OfferTour, User, OfferChangedJurisdiction
from visual.util import flash_errors
from .forms import MultitourFilter, MultitoursMovedFilter

from .. import mod, roles_required


class MultitourForm(FlaskForm):
    title_ru = StringField('Название')
    title_en = StringField('Название')
    title_de = StringField('Название')
    title_fr = StringField('Название')
    hidden = BooleanField('Скрыто')
    keep_position = BooleanField('Сохранение позиции')
    folder_id = SelectField('Папка')
    options = TextAreaField('template_data')


@mod.route('/multitours/')
@mod.route('/users/<int:user_id>/multitours/')
def multitours(user_id=None):
    folder_id = request.args.get('folder_id', None)
    filters = MultitourFilter(request.args)

    q = Offer.query.filter(Offer.type == 'multitour')\
        .options(db.joinedload(Offer.folder), db.joinedload(Offer.user))

    if filters.sort.data == 'title':
        q = q.order_by(Offer.title_ru)
    else:
        q = q.order_by(Offer.created.desc())

    if filters.search.data:
        q = q.filter(Offer.title_ru.ilike('%' + filters.search.data + '%'))

    if folder_id:
        q = q.filter(Offer.folder_id==folder_id)

    if user_id:
        user = User.query.get_or_404(user_id)
        q = q.filter(Offer.user_id == user.id)
    else:
        user = None

    offers = q.paginate(per_page=40, error_out=False)

    return render_template('admin/multitours/index.html', offers=offers, filters=filters, user=user)


@mod.route('/multitours/<int:offer_id>/edit/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/multitours/<int:offer_id>/edit/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/multitours/new', methods=('GET', 'POST'))
@roles_required('tours')
def multitour_edit(user_id=None, offer_id=None):
    if user_id:
        user = User.query.get_or_404(user_id, description='Пользователь не найден.')
    else:
        user = None

    if offer_id is None:
        if not user:
            abort(400, 'Неизвестно, какому юзеру делать мультитур')
        folder_id = request.values.get('folder_id')
        if folder_id == '0':
            folder_id = None
        offer = Offer(
            user_id=user.id, created_by=current_user.id,
            folder_id=folder_id,
            type='multitour', template='common', template_data={}
        )
        offer.user = user
    else:
        offer = Offer.query.get_or_404(offer_id)

    form = MultitourForm(obj=offer)
    form.folder_id.choices = [('0', 'Корень')] + [(str(f.id), f.title) for f in offer.user.folders]

    if form.validate_on_submit():
        if form.folder_id.data == '0':
            form.folder_id.data = None
        form.populate_obj(offer)
        errors = 0
        try:
            offer.template_data = json.loads(form.options.data)
        except ValueError as e:
            flash('Ошибка в options: {}'.format(str(e)), 'danger')
            errors += 1

        if not errors:
            flag_modified(offer, 'template_data')
            db.session.add(offer)
            db.session.commit()
            if request.values.get('then') == 'tours':
                return redirect(url_for('.multitour_tours', offer_id=offer.id, user_id=user_id))
            else:
                return redirect(url_for('.multitours', user_id=user_id))
    else:
        flash_errors(form)

    form.options.data = json.dumps(offer.template_data, indent=4, ensure_ascii=True, sort_keys=True)

    return render_template('admin/multitours/edit.html', offer=offer, user=user, form=form)


@mod.route('/multitours/<int:offer_id>/contents/', methods=('GET', 'POST', ))
@mod.route('/users/<int:user_id>/multitours/<int:offer_id>/contents/', methods=('GET', 'POST', ))
@roles_required('tours')
def multitour_tours(offer_id, user_id=None):
    if user_id:
        user = User.query.get_or_404(user_id)
    else:
        user = None

    offer = Offer.query.get_or_404(offer_id)

    if request.method == 'POST':
        if not request.json:
            abort(400, 'No input data')

        OfferTour.query.filter_by(offer_id=offer.id).delete()
        sort = 0
        resp = []
        for of in request.json:
            sort += 1
            offertour = OfferTour(offer_id=offer.id, tour_id=of['tour_id'], sort=sort, title=of.get('title'))
            db.session.add(offertour)
            resp.append(offertour.api_repr())
        offer.cnt_tours = sort
        db.session.commit()

        return jsonify({'result': resp})

    return render_template('admin/multitours/tours.html', offer=offer, user=user)


@mod.route('/multitours/<int:offer_id>/delete/', methods=('POST', ))
@mod.route('/users/<int:user_id>/multitours/<int:offer_id>/delete/', methods=('POST', ))
@roles_required('tours')
def multitour_delete(offer_id, user_id=None):

    offer = Offer.query.get_or_404(offer_id)
    db.session.delete(offer)
    db.session.commit()

    return redirect(url_for('.multitours', user_id=user_id))


@mod.route('/multitours_moved/')
def multitours_moved():
    search = MultitoursMovedFilter(request.args)
    q = db.session.query(OfferChangedJurisdiction)
    if request.args.get('search_by') == 'local_id':
        try:
            r = int(search.search_field.data)
            q = q.filter(OfferChangedJurisdiction.local_id == search.search_field.data)
        except:
            flash('Должно быть число', 'danger')


    if request.args.get('search_by') == 'remote_id':
        try:
            r = int(search.search_field.data)
            q = q.filter(OfferChangedJurisdiction.remote_id == search.search_field.data)
        except:
            flash('Должно быть число', 'danger')

    if request.args.get('search_by') == 'server':
        try:
            r = str(search.search_field.data)
            q = q.filter(OfferChangedJurisdiction.moved_to == search.search_field.data)
        except:
            flash('Должна быть строка', 'danger')

    if request.args.get('search_by') == 'created':
        try:
            start = datetime.strptime(search.search_field.data, '%d.%m.%Y')
            finish = start + timedelta(hours = 24)
            q = q.filter(db.and_(OfferChangedJurisdiction.created >= start,OfferChangedJurisdiction.created <=finish))
        except:
            flash('Неверный формат даты', 'danger')
    multitours = q.paginate(per_page=50, error_out=False)
    return render_template('admin/multitours/multitours_moved.html', multitours=multitours, form=search)
