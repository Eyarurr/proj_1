from flask import render_template, redirect, url_for, request

from visual.core import db
from visual.util import flash_errors
from visual.models import Vacancy

from .. import mod, roles_required

from .forms import VacancyForm


@mod.route('/vacancies/')
@mod.route('/vacancies/<lang>')
def vacancies(lang='ru'):
    vacancies = Vacancy.query.filter_by(lang=lang).order_by(Vacancy.sort).all()

    stats = {
        lang: count
        for lang, count in db.session.query(Vacancy.lang, db.func.count()).group_by(Vacancy.lang).all()
    }

    return render_template('admin/vacancies/index.html', vacancies=vacancies, lang=lang, stats=stats)


@mod.route('/vacancies/<lang>/new/', methods=['GET', 'POST'])
@mod.route('/vacancies/<lang>/<int:vacancy_id>/edit/', methods=('GET', 'POST'))
@roles_required('vacancies')
def vacancy_edit(lang, vacancy_id=None):
    if vacancy_id:
        vacancy = Vacancy.query.filter_by(lang=lang, id=vacancy_id).first_or_404()
        form = VacancyForm(obj=vacancy)
    else:
        vacancy = Vacancy(lang=lang)
        vacancy.sort = (db.session.query(db.func.min(Vacancy.sort)).scalar() or 0) - 1
        form = VacancyForm(obj=vacancy)

    if form.validate_on_submit():
        db.session.add(vacancy)
        db.session.flush()

        form.populate_obj(vacancy)

        db.session.commit()

        return redirect(url_for('.vacancies', lang=vacancy.lang))
    else:
        flash_errors(form)

    return render_template('admin/vacancies/edit.html', vacancy=vacancy, form=form)


@mod.route('/vacancies/<int:vacancy_id>/delete/', methods=('POST',))
@roles_required('vacancies')
def vacancy_delete(vacancy_id):
    vacancy = Vacancy.query.get_or_404(vacancy_id)

    db.session.delete(vacancy)
    db.session.commit()

    return redirect(url_for('.vacancies', lang=vacancy.lang))


@mod.route('/vacancies/<lang>/reorder/', methods=('POST',))
@roles_required('vacancies')
def vacancies_reorder(lang):
    for k, v in request.form.items():
        if k.startswith('sort.'):
            db.session.execute(
                'UPDATE %s SET sort = :sort WHERE lang = :lang AND id = :id' % Vacancy.__tablename__,
                {'id': k[5:], 'sort': v, 'lang': lang}
            )
    db.session.commit()

    return 'om-nom-nom!'
