from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm.attributes import flag_modified

from visual.core import db
from visual.models import Tour
from .. import mod, roles_required


@mod.route('/tours/<int:tour_id>/skyboxes/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/skyboxes/', methods=('GET', 'POST'))
def tour_skyboxes(tour_id, user_id=None):
    tour = Tour.query.get_or_404(tour_id)

    if request.method == 'POST':
        if not current_user.has_role('tours'):
            flash('У вас нет прав на редактирование туров.', 'danger')
            return redirect(url_for('.tour_skyboxes', tour_id=tour_id, user_id=user_id))

        tour.meta.setdefault('skyboxes', {})

        # Удаляем все свойства disabled из скайбоксов
        for skybox_id, skybox in tour.meta.get('skyboxes', {}).items():
            if 'disabled' in skybox:
                del skybox['disabled']

        if request.form.getlist('disabled'):
            for skybox_id in request.form.getlist('disabled'):
                tour.meta['skyboxes'].setdefault(skybox_id, {})['disabled'] = True

        # Подписи
        for k, v in request.form.items():
            if k.startswith('title.'):
                skybox_id = k[6:]
                if v.strip() != '':
                    tour.meta['skyboxes'].setdefault(skybox_id, {})['title'] = v.strip()
                else:
                    tour.meta['skyboxes'].get(skybox_id, {}).pop('title', None)

        if not tour.meta['skyboxes']:
            tour.meta.pop('skyboxes', None)

        # Удаляем пустые объекты Skybox
        skyboxes = {skybox_id: skybox for skybox_id, skybox in tour.meta['skyboxes'].items() if skybox}
        tour.meta['skyboxes'] = skyboxes

        flag_modified(tour, 'meta')
        db.session.commit()

        return redirect(url_for('.tour_skyboxes', tour_id=tour_id, user_id=user_id))

    return render_template('admin/tours/skyboxes.html', tour=tour, user_id=user_id)

