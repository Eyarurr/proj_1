import os
from datetime import datetime

from flask import render_template, request, jsonify, url_for, redirect, flash
from flask_login import current_user

from visual.core import db
from visual.models import Tour, Footage, User
from .. import mod


@mod.route("/users/<int:user_id>/tours/create/new/")
def tour_create_inside(user_id=None):
    user = User.query.get_or_404(user_id, description='Пользователь не найден')

    footage = Footage(
        created_by=current_user.id,
        user_id=user.id,
        type='virtual',
        _status='loading',
        meta={
            "_loading": {
                "models": [],
                "options": {
                    "render_type": "vray", "model_lowpoly": True, "coords_from_obj": True,
                    "dollhouse": True, "lang": "ru"
                },
                "skyboxes": {},
                "floor_heights": {}
            }
        }
    )
    db.session.add(footage)
    db.session.flush()

    folder_id = request.args.get('folder_id')
    if folder_id == '' or folder_id == '0':
        folder_id = None

    tour = Tour(
        user_id=user.id,
        created_by=current_user.id,
        footage_id=footage.id,
        folder_id=folder_id,
        title='New tour {}'.format(datetime.now().strftime('%d.%m.%Y')),
        meta={}
    )
    db.session.add(tour)
    footage.mkdir()
    db.session.commit()
    os.makedirs(footage.in_files('_loading'), exist_ok=True)

    return render_template('admin/tours/create_inside.html', tour=tour)

    return redirect(url_for('.tours', user_id=user_id))
