import datetime

from visual.core import db
from visual.models import BROffice, TeamMember, User
from visual.util import flash_errors
from .forms import BROfficesFiltersForm, BROfficeEditForm
from flask import render_template, redirect, url_for, request

from .. import mod, roles_required


@mod.route('/bladerunner/offices')
@roles_required('br.super')
def br_offices():
    """
    Список офисов
    """
    filters = BROfficesFiltersForm(request.args)
    q = BROffice.query

    q = q.order_by(BROffice.created.desc())

    offices = q.paginate(per_page=50)

    return render_template('admin/bladerunner/offices.html', offices=offices, filters=filters)


@mod.route('/bladerunner/offices/new', methods=('GET', 'POST'))
@mod.route('/bladerunner/offices/<int:office_id>/edit', methods=('GET', 'POST'))
@roles_required('br.super')
def br_office_edit(office_id=None):
    """
    Редактор офиса
    """
    def populate_fields(form, office):
        has_errors = False
        office.coords = [form.coords_lat.data, form.coords_lon.data]

        if form.manager_email.data:
            manager = TeamMember.query.join(User).filter(db.func.lower(User.email) == form.manager_email.data.lower()).first()
            if not manager or 'br.super' not in manager.roles:
                form.manager_email.errors.append(f'Член команды с ролью br.super и почтой "{form.manager_email.data.lower()}" не найден')
                has_errors = True
            else:
                office.manager_id = manager.user_id

        try:
            datetime.time.fromisoformat(form.work_start.data)
        except ValueError:
            form.work_start.errors.append('Неправильное время начала работы. Нужно в формате HH:MM:SS+TZ:TZ.')
            has_errors = False

        try:
            datetime.time.fromisoformat(form.work_end.data)
        except ValueError:
            form.work_end.errors.append('Неправильное время окончания работы. Нужно в формате HH:MM:SS+TZ:TZ.')
            has_errors = False

        return not has_errors

    if office_id:
        office = BROffice.query.get_or_404(office_id)
    else:
        office = BROffice()

    form = BROfficeEditForm(obj=office)

    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(office)
            if populate_fields(form, office):
                db.session.add(office)
                db.session.commit()
                return redirect(url_for('.br_offices'))
        print('THERE WERE ERRORS')
        flash_errors(form)
    else:
        if office.coords:
            form.coords_lat.data, form.coords_lon.data = office.coords
        if office.manager_id:
            form.manager_email.data = office.manager.email

    return render_template('admin/bladerunner/office_edit.html', office=office, form=form)


@mod.route('/bladerunner/offices/<int:office_id>/delete', methods=('POST', ))
@roles_required('br.super')
def br_office_delete(office_id):
    """
    Удалить офис
    """
    office = BROffice.query.get_or_404(office_id)
    db.session.delete(office)
    db.session.commit()

    return redirect(url_for('.br_offices'))


