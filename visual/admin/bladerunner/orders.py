import os
import shutil
import json
import datetime

from flask import render_template, redirect, url_for, request, current_app, flash
from flask_login import current_user
from sqlalchemy.orm.attributes import flag_modified

from visual.core import db, queue, queue_quick
from visual.models import BROffice, BROperator, BROrder, BROrderAsset, User, Tour, TourVideo
from visual.util import flash_errors
from .forms import BROrdersFiltersForm, BROrderCreateForm, BROrderAssetFiltersForm, BROrderAssetEditForm

from .. import mod, roles_required

def count_order_assets(order):
    order_assets = {}
    for type in BROrderAsset.TYPES:
        assets_count = BROrderAsset.query.filter_by(order_id=order.id, type=type).count()
        if assets_count != 0:
            order_assets[type] = assets_count
    order.cnt_assets = order_assets
    flag_modified(order, 'cnt_assets')
    db.session.commit()


@mod.route('/bladerunner/orders')
@mod.route('/bladerunner/<int:office_id>/orders')
@roles_required('br.super')
def br_orders(office_id=None):
    """
    Список заказов.
    """
    filters = BROrdersFiltersForm(request.args)
    office = None
    if office_id:
        office = BROffice.query.get_or_404(office_id)

    q = BROrder.query
    if office:
        q = q.filter(BROrder.office_id == office.id)

    q = q.order_by(BROrder.created.desc())

    orders = q.paginate(per_page=50)

    return render_template('admin/bladerunner/orders.html', orders=orders, filters=filters, office=office)


@mod.route('/bladerunner/<int:office_id>/orders/new', methods=('GET', 'POST'))
@mod.route('/bladerunner/<int:office_id>/orders/<int:order_id>/edit', methods=('GET', 'POST'))
@roles_required('br.super')
def br_order_edit(office_id, order_id=None):
    """
    Создать заказ для офиса office_id
    """
    def populate_fields(form, order):
        order.coords = [form.coords_lat.data, form.coords_lon.data]

        if form.start.data == '':
            order.start = None
        else:
            try:
                order.start = datetime.datetime.fromisoformat(form.start.data)
            except ValueError as e:
                form.start.errors.append(f'Неправильное время начала заказа."{form.start.data}" Нужно в формате YYYY-MM-DD HH:MM:SS+TZ:TZ.')
                return False

        if form.operator_id.data == '0':
            order.operator_id = None

        if form.customer_email.data:
            customer = User.query.filter(db.func.lower(User.email) == form.customer_email.data.lower()).first()
            if not customer:
                form.manager_email.errors.append(f'Юзер с почтой "{form.customer_email.data}" не найден.')
                return False
            order.customer_id = customer.id

        if form.contacts.data:
            order.contacts = json.loads(form.contacts.data)
        else:
            order.contacts = None
        return True

    office = BROffice.query.get_or_404(office_id)
    if order_id:
        order = BROrder.query.get_or_404(order_id)
    else:
        order = BROrder(office_id=office.id, status='scheduled')

    form = BROrderCreateForm(obj=order)
    q_operators = BROperator.query.join(User).filter(BROperator.office_id == office.id).order_by(User.name)
    form.operator_id.choices = [(0, 'Без оператора')] + [(o.user_id, o.user.name) for o in q_operators.all()]

    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(order)
            if populate_fields(form, order):
                db.session.add(order)
                db.session.commit()
                return redirect(url_for('.br_orders', office_id=office.id))
        flash_errors(form)
    else:
        if order.coords:
            form.coords_lat.data, form.coords_lon.data = order.coords
        if type(order.contacts) is dict:
            form.contacts.data = [order.contacts]
        form.contacts.data = json.dumps(form.contacts.data, ensure_ascii=False, indent=4)
        if order.customer_id:
            form.customer_email.data = order.customer.email

    return render_template('admin/bladerunner/order_edit.html', office=office, order=order, form=form)


@mod.route('/bladerunner/assets')
@mod.route('/bladerunner/<int:office_id>/orders/assets')
@mod.route('/bladerunner/<int:office_id>/orders/<int:order_id>/assets')
@roles_required('br.super', 'br.operator')
def br_assets(office_id=None, order_id=None):
    order = None
    office = None
    filters = BROrderAssetFiltersForm(request.args)
    q = db.session.query(BROrderAsset, BROrder, BROffice).join(BROrder, BROrderAsset.order_id == BROrder.id).outerjoin(
        BROffice, BROrder.office_id == BROffice.id)
    if office_id:
        office = BROffice.query.get(office_id)
        q = q.filter(BROffice.id == office_id)
    if order_id:
        order = BROrder.query.get(order_id)
        q = q.filter(BROrder.id == order_id)

    q = q.order_by(BROrderAsset.created.desc())
    assets = q.paginate(per_page=50)
    return render_template('admin/bladerunner/assets.html', assets=assets, order=order, office=office, filters=filters)


@mod.route('/bladerunner/<int:office_id>/orders/<int:order_id>/assets/<int:asset_id>/edit', methods=['GET', 'POST'])
@mod.route('/bladerunner/<office_id>/orders/<order_id>/assets/new', methods=['GET', 'POST'])
@roles_required('br.super', 'br.operator')
def br_asset_edit(office_id, order_id, asset_id=None):
    def populate_fields(form, asset):
        if form.operator_id.data == '0':
            form.operator_id.errors.append('Должен быть выбран оператор')
            return False

        if form.tour_id.data and form.tour_video_id.data:
            form.tour_id.errors.append('Укажите тур id, либо тур_видео id')
            return False

        if asset.type == 'tour':
            if not asset.tour_id:
                form.type.errors.append('Не заполнен tour_id')
                return False
            tour = Tour.query.get(asset.tour_id)
            if not tour:
                form.tour_id.errors.append(f'Указан id несуществующего тура: {asset.tour_id}')
                return False

            if asset.s3key:
                if not asset.s3key.startswith('tourvideos'):
                    asset.delete_files()
                asset.s3key = None
                asset.preview_s3key = None
            asset.size = None
            asset.height = None
            asset.width = None
            asset.duration = None
        else:
            asset.tour_id = None

        if asset.type == 'tour_video':
            if not asset.tour_video_id:
                form.type.errors.append('Не заполнен tour_video_id')
                return False
            tour_video = TourVideo.query.get(asset.tour_video_id)
            if not tour_video:
                form.tour_id.errors.append(f'Указан id несуществующего tour_video: {asset.tour_video_id}')
                return False
            if asset.s3key:
                if not asset.s3key.startswith('tourvideos'):
                    asset.delete_files()
            asset.s3key = tour_video.video_s3_key
            asset.preview_s3key = tour_video.preview_s3_key
            asset.size = tour_video.size
            asset.height = tour_video.height
            asset.width = tour_video.width
            asset.duration = tour_video.duration
        else:
            asset.tour_video_id = None

        # удаляем старый добавляем новый файл
        upload_file = request.files.get('upload_file')
        if upload_file:
            if asset.s3key and not asset.s3key.startswith('tourvideos'):
                asset.delete_files()

            if asset.type not in ('tour', 'tour_video'):
                asset.save_file(upload_file)
        return True

    office = BROffice.query.get_or_404(office_id)
    order = BROrder.query.get_or_404(order_id)
    if asset_id:
        asset = BROrderAsset.query.get_or_404(asset_id)
    else:
        asset = BROrderAsset(order_id=order.id)

    form = BROrderAssetEditForm(obj=asset)
    q_operators = BROperator.query.join(User).filter(BROperator.office_id == office.id).order_by(User.name)
    form.operator_id.choices = [(0, 'Без оператора')] + [(o.user_id, o.user.name) for o in q_operators.all()]

    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(asset)
            if populate_fields(form, asset):
                db.session.add(asset)
                db.session.commit()
                count_order_assets(order)
                return redirect(url_for('.br_assets', office_id=office.id, order_id=order.id))
            else:
                flash_errors(form)
        else:
            flash_errors(form)
    return render_template('admin/bladerunner/asset_edit.html', form=form, asset=asset, office=office, order=order)


@mod.route('/bladerunner/<int:office_id>/orders/<int:order_id>/assets/<int:asset_id>/delete', methods=['POST'])
@roles_required('br.super', 'br.operator')
def br_asset_delete(asset_id, office_id, order_id):
    asset = BROrderAsset.query.get_or_404(asset_id)
    if asset.s3key:
        if not asset.s3key.startswith('tourvideos'):
            asset.delete_files()


    db.session.delete(asset)
    order = BROrder.query.get_or_404(order_id)
    count_order_assets(order)
    db.session.commit()
    return redirect(url_for('.br_assets', office_id=office_id, order_id=order_id))


@mod.route('/bladerunner/<int:office_id>/orders/<int:order_id>/download/')
@roles_required('br.super', 'br.operator')
def br_assets_download(office_id=None, order_id=None):
    """Ставит в очередь queue_quick архивирование ассетов заказа. (всех кроме tour)"""
    dst = os.path.join(current_app.static_folder, 'admin', 'downloads')

    assets_size = db.session.query(db.func.sum(BROrderAsset.size).label('size')). \
        filter(BROrderAsset.order_id == order_id, BROrderAsset.type != 'tour').scalar()

    if not assets_size:
        flash('Не удалось создать задачу на упаковку ассетов: ассетов не найдено.', 'warning')
    elif assets_size > 0.9 * shutil.disk_usage(dst)[2]:
        flash('Не удалось создать задачу на упаковку ассетов заказа из-за нехватки места. Дёрните админов.', 'danger')
    else:
        job = queue_quick.enqueue('visual.jobs.admin.zip_brorder_assets', order_id, current_user.id,
                                  job_timeout=current_app.config['BUILDER_JOB_TIMEOUT'])
        if job is None:
            # Задача уже успела завершиться (скорее всего, какой-то хуйнёй)
            flash('Не удалось создать задачу на упаковку ассетов заказа, что-то с очередями. Дёрните админов.', 'danger')
        else:
            flash('Ассеты упаковываются в ZIP. Когда архив будет готов, вам на почту {} придёт ссылка на его скачивание.'
                  .format(current_user.email), 'success')

    return redirect(url_for('.br_orders', office_id=office_id, order_id=order_id))
