import json
import random

from flask import render_template, redirect, request, url_for, flash, make_response, current_app
from wtforms import StringField
from flask_login import login_user, current_user
from sqlalchemy.exc import IntegrityError
import stripe

from visual.core import db, products
from visual.util import flash_errors
from visual.models import User, Tag

from .. import mod, roles_required
from .forms import TagEditForm


@mod.route('/users/<int:user_id>/tags/')
def user_tags(user_id):
    user = User.query.get_or_404(user_id)

    tags = Tag.query.filter_by(user_id=user.id).order_by(Tag.name).all()

    return render_template('admin/users/tags.html', user=user, tags=tags)


@mod.route('/users/<int:user_id>/tags/<int:tag_id>/', methods=['GET', 'POST'])
@mod.route('/users/<int:user_id>/tags/new/', methods=['GET', 'POST'])
def user_tag_edit(user_id, tag_id=None):
    def populate_fields(form, tag):
        q = Tag.query.filter_by(name=form.name.data)
        if tag.id:
            q = q.filter(Tag.id != tag.id)
        if q.first():
            form.name.errors.append('Тег с таким name уже есть.')
            return False

        # Собираем display_dict
        display_dict = {}
        for field in form:
            if field.name.startswith('dd_k_'):
                val_field = getattr(form, field.name.replace('_k_', '_v_'))
                if field.data:
                    display_dict[field.data] = val_field.data

        tag.display_dict = display_dict or None

        return True

    user = User.query.get_or_404(user_id)
    if tag_id:
        tag = Tag.query.filter_by(user_id=user.id, id=tag_id).first_or_404()
    else:
        tag = Tag(user_id=user.id)

    # Создаём копию класса формы и добавляем туда поля для display_dict: из существующих данных
    # и новые поля, которые добавились JSом в форме на фронте
    Form = type('TagEditForm', TagEditForm.__bases__, dict(TagEditForm.__dict__))
    if tag.display_dict:
        for i, (k, v) in enumerate(tag.display_dict.items()):
            setattr(Form, f'dd_k_{i}', StringField(k, default=k))
            setattr(Form, f'dd_v_{i}', StringField(v, default=v))
    for k, v in request.form.items():
        if k.startswith('dd_k_') and not hasattr(Form, k):
            setattr(Form, k, StringField(k, default=v))
        if k.startswith('dd_v_') and not hasattr(Form, k):
            setattr(Form, k, StringField(k, default=v))

    form = Form(obj=tag)

    if form.validate_on_submit():
        form.populate_obj(tag)
        if populate_fields(form, tag):
            db.session.add(tag)
            db.session.commit()
            return redirect(url_for('.user_tags', user_id=user.id))
        flash_errors(form)

    return render_template('admin/users/tag_edit.html', user=user, tag=tag, form=form)


@mod.route('/users/<int:user_id>/tags/<int:tag_id>/delete', methods=['POST'])
def user_tag_delete(user_id, tag_id):
    user = User.query.get_or_404(user_id)
    tag = Tag.query.filter_by(user_id=user.id, id=tag_id).first_or_404()

    db.session.delete(tag)
    db.session.commit()

    return redirect(url_for('.user_tags', user_id=user.id))

