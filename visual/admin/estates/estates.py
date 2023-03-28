import boto3
import botocore
from sqlalchemy.orm.attributes import flag_modified
from flask_login import current_user

from visual.core import db
from visual.models import User, Estate, EstateAsset, TourVideo, BROrderAsset, BROrder
from flask import render_template, redirect, url_for, request, current_app

from .forms import EstateAssetEditForm, FilterEstatesForm, EstatesAssetsFilterForm, AddEstateForm
from .. import mod, roles_required
from ...util import flash_errors

def count_assets(estate):
    order_assets = {}
    for type in EstateAsset.TYPES:
        assets_count = EstateAsset.query.filter_by(estate_id=estate.id, type=type).count()
        if assets_count != 0:
            order_assets[type] = assets_count
    estate.cnt_assets = order_assets
    flag_modified(estate, 'cnt_assets')
    db.session.commit()


@mod.route('/estates', methods=['POST', 'GET'])
@mod.route('/estates/<int:user_id>')
@roles_required('users')
def estates(user_id=None):
    """
    Список объектов недвижимости
    """
    def validate_form(form):
        if form.select.data == 'id':
            try:
                int(form.search.data)
            except ValueError:
                return False
        return True

    user=None
    q = Estate.query.options(db.joinedload(Estate.user),db.joinedload(Estate.tags))
    if user_id:
        user = User.query.get_or_404(user_id)
        q = q.filter(Estate.user_id == user.id)

    form = FilterEstatesForm(request.args)
    pattern = form.search.data
    select = form.select.data

    if validate_form(form):
        if select == 'title':
            q = q.filter(Estate.title.ilike(f'%{pattern}%'))
        elif select == 'id':
            q = q.filter(Estate.id == pattern)
        elif select == 'user_name':
            q = q.join(User).filter(User.name.ilike(f'%{pattern}%'))

    q = q.order_by(Estate.created.desc())
    estates = q.paginate(per_page=50)
    return render_template('admin/estates/estates.html', estates = estates, filters=form, user=user)


@mod.route('/estates/new', methods=['POST', 'GET'])
@mod.route('/estates/<int:estate_id>/edit', methods=['POST', 'GET'])
@roles_required('users')
def estates_edit(estate_id=None):
    """
    Список объектов недвижимости
    """
    def populate_fields(estate, form):
        if not estate.user_id:
            estate.user_id = current_user.id
        if not estate.title:
            form.title.errors.append('Укажите название объекта')
            return False
        return True

    if estate_id:
        estate = Estate.query.get_or_404(estate_id)
    else:
        estate = Estate()
    form = AddEstateForm(obj=estate)
    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(estate)
            if  populate_fields(estate, form):
                db.session.add(estate)
                db.session.commit()
                return redirect(url_for('.estates'))
            else:
                flash_errors(form)
        else:
            flash_errors(form)
    return render_template('admin/estates/estate_edit.html', form=form, estate=estate)


@mod.route('/estates/<int:estate_id>/delete', methods=['POST', 'GET'])
@roles_required('users')
def estate_delete(estate_id):
    estate = Estate.query.get_or_404(estate_id)
    assets = EstateAsset.query.filter_by(estate_id=estate.id).all()
    for asset in assets:
        asset.delete_files()
    db.session.delete(estate)
    db.session.commit()
    return redirect(url_for('.estates'))



@mod.route('/estates/<int:estate_id>/assets')
@roles_required('users')
def estate_assets(estate_id):
    filters = EstatesAssetsFilterForm(request.args)
    estate = Estate.query.get_or_404(estate_id)
    q = db.session.query(EstateAsset).filter_by(estate_id=estate.id)
    q = q.order_by(EstateAsset.created.desc())
    assets = q.paginate(per_page=50)
    return render_template('admin/estates/assets.html', assets=assets, filters=filters, estate=estate)


@mod.route('/estates/<int:estate_id>/assets/new', methods=('GET', 'POST'))
@mod.route('/estates/<int:estate_id>/assets/<int:asset_id>/edit', methods=('GET', 'POST'))
@roles_required('users')
def estates_assets_edit(estate_id, asset_id=None):

    def populate_fields(asset):
        if asset.type == 'tour':
            if asset.s3key:
                if not asset.s3key.startswith('tourvideos'):
                    asset.delete_files()
                asset.s3key = None
                asset.preview_s3key = None
            asset.size = None
            asset.height = None
            asset.width = None
            asset.duration = None
            asset.tour_video = None
        else:
            asset.tour_id = None

        if asset.type == 'tour_video':
            if not form.tour_video_id.data:
                form.type.errors.append('Не заполнен tour_video_id')
                return False
            tour_video = TourVideo.query.get(asset.tour_video_id)
            if asset.s3key:
                if not asset.s3key.startswith('tourvideos'):
                    asset.delete_files()
            asset.s3key = tour_video.video_s3_key
            asset.preview_s3key = tour_video.preview_s3_key
            asset.size = tour_video.size
            asset.height = tour_video.height
            asset.width = tour_video.width
            asset.duration = tour_video.duration
            asset.tour_id = None
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

    estate = Estate.query.get(estate_id)
    if asset_id:
        asset = EstateAsset.query.get_or_404(asset_id)
    else:
        asset = EstateAsset(estate_id=estate.id)

    form = EstateAssetEditForm(obj=asset)
    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(asset)
            if populate_fields(asset):
                db.session.add(asset)
                db.session.commit()
                estate.cnt_assets = count_assets(estate)
                return redirect(url_for('.estate_assets', estate_id=estate.id))
            else:
                flash_errors(form)
        else:
            flash_errors(form)
    return render_template('admin/estates/asset_edit.html', form=form, asset=asset)


@mod.route('/estates/<int:estate_id>/assets/<int:asset_id>/delete', methods=['POST'])
@roles_required('users')
def estates_assets_delete(asset_id, estate_id):
    asset = EstateAsset.query.get_or_404(asset_id)
    if asset.s3key:
        if not asset.s3key.startswith('tourvideos'):
            asset.delete_files()
            # delete_asset_from_s3(asset)
    db.session.delete(asset)
    order = Estate.query.get_or_404(estate_id)
    count_assets(order)
    db.session.commit()
    return redirect(url_for('.estate_assets', estate_id=estate_id))


@mod.route('/estates/<int:estate_id>/assets/copy', methods=('GET', 'POST'))
@roles_required('users')
def estates_assets_copy(estate_id):
    estate = Estate.query.get_or_404(estate_id)
    id_order = request.args.get('id_order')
    br_assets = 1
    order = 0
    if id_order:
        order = BROrder.query.get_or_404(id_order)
        br_assets = BROrderAsset.query.filter(BROrderAsset.order_id == order.id).all()
    if request.method == 'POST':
        form = request.form
        for br_order_asset_id in form.getlist('for_copy'):
            br_asset = BROrderAsset.query.get(br_order_asset_id)
            estate.create_asset_from_brorderasset(br_asset)
        db.session.commit()
        return redirect(url_for('.estate_assets', estate_id=estate.id))
    return render_template('admin/estates/assets_copy.html', br_assets=br_assets, estate=estate)

