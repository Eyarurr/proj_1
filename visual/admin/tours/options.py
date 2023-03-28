from flask import render_template, request, redirect, url_for, flash, send_file, jsonify, current_app
from sqlalchemy.orm.attributes import flag_modified

from visual.core import db
from visual.models import Tour
from .. import mod, roles_required


@mod.route('/tours/<int:tour_id>/options/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/options/', methods=('GET', 'POST'))
@roles_required('tours')
def tour_options(tour_id, user_id=None):
    tour = Tour.query.get_or_404(tour_id)

    def _bool(v):
        return v == 'True'

    def _rgb(v):
        rgba = v[5:-1].split(',')
        return [int(rgba[x]) for x in range(3)] + [float(rgba[3])]

    def _disable(v):
        return v.split(',')

    def _vector2(v):
        vector2 = v.split(',')
        return [float(vector2[x]) for x in range(2)]

    OPTIONS = {
        # общие опции
        'disable': _disable,
        'active_meshes_look_fill': _rgb,
        'active_meshes_hover_fill': _rgb,
        # опции inside-туров
        'cursor_color': _rgb,
        'fov': int,
        'fov_min': int,
        'fov_max': int,
        'mapshow': str,
        'help': _bool,
        'mapbg': _rgb,
        'roulette_color': _rgb,
        'roulette_text_color': _rgb,
        'markers_color': _rgb,
        'markers': _bool,
        'mapmarkers': str,
        'navigator_show': str,
        'skybox_preloader': str,
        'pan_speed': int,
        'walk': str,
        'look_limit_up': int,
        'look_limit_down': int,
        'dollhouse_bg_color': _rgb,
        # опции outside-туров
        'key_pan_speed': _vector2,
        'key_rotate_speed': _vector2,
        'mouse_pan_speed': _vector2,
        'mouse_rotate_speed': _vector2,
        'gpu_raycast_max_mesh_faces': int,
        'max_resolution': int,
        'quality_improve_time': int,
        'scroll': str,
    }

    if 'options' not in tour.meta:
        tour.meta['options'] = {}

    if request.method == 'POST':
        for k, v in request.form.items():
            if k not in OPTIONS:
                continue
            if v == '':
                tour.meta['options'].pop(k, None)
            else:
                tour.meta['options'][k] = OPTIONS[k](v)

        tour.save_features()
        flag_modified(tour, 'meta')
        db.session.commit()
        flash('Настройки сохранены', 'success')
        return redirect(url_for('.tour_options', tour_id=tour.id, user_id=user_id))

    return render_template('admin/tours/options.html', tour=tour, user_id=user_id)
