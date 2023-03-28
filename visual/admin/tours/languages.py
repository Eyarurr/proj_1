from flask import render_template, request, redirect, url_for
from sqlalchemy.orm.attributes import flag_modified

from visual.core import db
from visual.models import Tour
from .. import mod, roles_required


@mod.route('/tours/<int:tour_id>/languages/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/languages/', methods=('GET', 'POST'))
def tour_languages(tour_id, user_id=None):
    tour = Tour.query.get_or_404(tour_id)

    return render_template('admin/tours/languages.html', tour=tour, user_id=user_id)


@mod.route('/tours/<int:tour_id>/languages/add/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/languages/add/', methods=('GET', 'POST'))
@roles_required('tours')
def tour_language_edit(tour_id, user_id=None):
    tour = Tour.query.get_or_404(tour_id)

    tour.meta.setdefault('languages', {})

    code = request.form.get('code').lower()
    tour.meta['languages'][code] = request.form.get('title')
    if not tour.meta.get('default_lang'):
        tour.meta['default_lang'] = request.form.get('code').lower()

    flag_modified(tour, 'meta')
    db.session.commit()

    return redirect(url_for('.tour_languages', tour_id=tour.id, user_id=user_id))


@mod.route('/tours/<int:tour_id>/languages/delete/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/languages/delete/', methods=('GET', 'POST'))
@roles_required('tours')
def tour_language_delete(tour_id, user_id=None):
    tour = Tour.query.get_or_404(tour_id)

    tour.meta.setdefault('languages', {})
    code = request.form.get('code')
    tour.meta['languages'].pop(code, None)
    if tour.meta.get('default_lang') == code:
        del tour.meta['default_lang']

    flag_modified(tour, 'meta')
    db.session.commit()

    return redirect(url_for('.tour_languages', tour_id=tour.id, user_id=user_id))


@mod.route('/tours/<int:tour_id>/languages/default/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/languages/default/', methods=('GET', 'POST'))
@roles_required('tours')
def tour_language_default(tour_id, user_id=None):
    tour = Tour.query.get_or_404(tour_id)

    code = request.form.get('code')
    tour.meta['default_lang'] = code

    flag_modified(tour, 'meta')
    db.session.commit()

    return redirect(url_for('.tour_languages', tour_id=tour.id, user_id=user_id))
