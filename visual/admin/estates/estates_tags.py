from visual.core import db
from visual.models import Estate, EstateTag, Tag
from flask import render_template, redirect, url_for, request

from .forms import  EtagEditForm, FormTag, SelectEstatesForm, FilterEtagForm
from .. import mod, roles_required
from ...api3 import api_response
from ...util import flash_errors


@mod.route('/estates/<int:estate_id>/etags')
@roles_required('users')
def estates_etags(estate_id):
    estate = Estate.query.get_or_404(estate_id)

    filters = FilterEtagForm()
    form = SelectEstatesForm()
    estates= Estate.query.filter(Estate.user_id == estate.user_id).all()
    form.parent_id.choices = [(0, '')] + [(_.id, _.title) for _ in estates]
    q = EstateTag.query.options(db.joinedload(EstateTag.tag)).filter_by(estate_id=estate.id)

    pattern = request.args.get('search')
    selector = request.args.get('select')
    if selector == 'label':
        q = q.join(Tag).filter(Tag.label.ilike(f'%{pattern}%'))
    elif selector == 'value':
        q = q.filter(EstateTag.value.ilike(f'%{pattern}%'))
    elif selector == 'name':
        q = q.join(Tag).filter(Tag.name.ilike(f'%{pattern}%'))

    estates_tags = q.paginate(per_page=50)
    return render_template('admin/estates/estates_tags.html', form=form, etags = estates_tags, filters=filters, estate=estate)


@mod.route('/estates/<int:estate_id>/etags/new', methods=('GET', 'POST'))
@mod.route('/estates/<int:estate_id>/etags/<int:etag_id>/edit', methods=('GET', 'POST'))
@roles_required('users')
def estates_etag_edit(estate_id, etag_id=None):

    def populate_fields(etag, form):
        tag = Tag.query.get(etag.tag_id)
        if not tag:
            form.tag_id.errors.append('Выбран пустое значение для тега или не заполнена таблица Tag')
            return False
        return True

    estate = Estate.query.get_or_404(estate_id)
    if etag_id:
        etag = EstateTag.query.get_or_404(etag_id)
    else:
        etag = EstateTag(estate_id=estate.id)

    form = EtagEditForm(obj=etag)
    form_tag = FormTag(obj=etag.tag)
    user_tags = Tag.query.filter_by(user_id=estate.user_id).all()
    form.tag_id.choices =[(0, '')] + [(_.id, _.name) for _ in user_tags]
    if request.method == 'POST':
        form.populate_obj(etag)
        if form.validate_on_submit():
            if populate_fields(etag, form):
                db.session.add(etag)
                db.session.commit()
                return redirect(url_for('.estates_etags', estate_id=estate.id))
            else:
                flash_errors(form)
        else:
            flash_errors(form)
    return render_template('admin/estates/estates_tag_edit.html', form=form, form_tag=form_tag, estate=estate)


@mod.route('/estates/<int:estate_id>/etag/<int:etag_id>/delete', methods=('GET', 'POST'))
@roles_required('users')
def estates_etag_delete(estate_id, etag_id):
    estate= Estate.query.get_or_404(estate_id)
    etag= EstateTag.query.filter(EstateTag.id == etag_id, EstateTag.estate_id == estate.id).first_or_404()
    db.session.delete(etag)
    db.session.commit()
    return redirect(url_for('.estates_etags', estate_id=estate_id))


@mod.route('/estates/<int:estate_id>/etags/delete', methods=('GET', 'POST'))
@roles_required('users')
def estates_etags_delete(estate_id):
    estate= Estate.query.get_or_404(estate_id)
    args = request.form.getlist('for_delete')
    tags = EstateTag.query.filter(EstateTag.id.in_(args), EstateTag.estate_id ==estate.id).all()
    for tag in tags:
        db.session.delete(tag)
    db.session.commit()
    return redirect(url_for('.estates_etags', estate_id=estate.id))


@mod.route('/estates/tag/<int:tag_id>', )
@roles_required('users')
def estates_get_tag(tag_id):
    tag  = Tag.query.filter_by(id=tag_id).first_or_404()
    return api_response(tag.api_repr())


@mod.route('/estates/<int:estate_id>/etags/multiple_tags', methods=('GET', 'POST'))
@roles_required('users')
def estates_etag_add_multiple_tags(estate_id):
    estate = Estate.query.get_or_404(estate_id)
    tags = Tag.query.filter(Tag.user_id == estate.user_id)
    if request.method == 'POST':
        form = request.form
        for tag_id in form.getlist('tag'):
            value = form.get(f'tag_val_{tag_id}')
            etag= EstateTag(estate_id=estate.id, tag_id=tag_id, value=value)
            db.session.add(etag)
        db.session.commit()
        return redirect(url_for('.estates_etags', estate_id=estate.id))
    return render_template('admin/estates/estates_tags_multiple.html', tags=tags, estate=estate)
