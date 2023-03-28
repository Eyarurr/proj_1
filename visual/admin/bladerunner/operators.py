import datetime

from flask_wtf import FlaskForm
from flask import render_template, redirect, url_for, request, flash, jsonify
from wtforms import StringField, TextAreaField, ValidationError, BooleanField, SelectField, IntegerField, FloatField, TimeField, DateField, DateTimeField
from wtforms.fields import EmailField
from wtforms import validators as v

from visual.core import db
from visual.models import BROffice, BROperator, BROrder, BROrderAsset, TeamMember, User
from visual.util import PhoneField, MultiCheckboxField, FiltersForm, flash_errors
from .forms import BROperatorsFiltersForm, BROperatorEditForm

from .. import mod, roles_required





@mod.route('/bladerunner/operators')
@mod.route('/bladerunner/<int:office_id>/operators')
@roles_required('br.super')
def br_operators(office_id=None):
    """
    Список операторов
    """
    filters = BROperatorsFiltersForm(request.args)
    office = None
    if office_id:
        office = BROffice.query.get_or_404(office_id)

    q = BROperator.query
    if office:
        q = q.filter(BROperator.office_id == office.id)

    q = q.join(User).order_by(User.name.desc())

    operators = q.paginate(per_page=50)

    return render_template('admin/bladerunner/operators.html', operators=operators, filters=filters, office=office)


@mod.route('/bladerunner/<int:office_id>/operators/new', methods=('GET', 'POST'))
@mod.route('/bladerunner/<int:office_id>/operators/<int:operator_id>/edit', methods=('GET', 'POST'))
@roles_required('br.super')
def br_operator_edit(office_id, operator_id=None):
    """
    Редактор офиса
    """
    def populate_fields(form, operator):
        has_errors = False
        if form.user_email.data:
            member = TeamMember.query.join(User).filter(db.func.lower(User.email) == form.user_email.data.lower()).first()
            if not member or 'br.operator' not in member.roles:
                form.user_email.errors.append(f'Член команды с ролью br.operator и почтой "{form.user_email.data.lower()}" не найден')
                has_errors = True
            else:
                q = BROperator.query.filter(BROperator.user_id == member.user_id)
                if operator.user_id:
                    q = q.filter(BROperator.office_id != office.id)
                other = q.first()
                if other:
                    form.user_email.errors.append(f'Этот оператор уже работает в офисе "{other.office.title or "Без названия"}". Сперва увольте его оттуда.')
                    has_errors = True
                else:
                    operator.user_id = member.user_id

        try:
            datetime.time.fromisoformat(form.work_start.data)
        except ValueError:
            form.work_start.errors.append('Неправильное время начала работы. Нужно в формате HH:MM:SS+TZ:TZ.')
            has_errors = True

        try:
            datetime.time.fromisoformat(form.work_end.data)
        except ValueError:
            form.work_end.errors.append('Неправильное время окончания работы. Нужно в формате HH:MM:SS+TZ:TZ.')
            has_errors = True

        return not has_errors

    office = BROffice.query.get_or_404(office_id)

    if operator_id:
        operator = BROperator.query.get_or_404(operator_id)
    else:
        operator = BROperator(office_id=office.id)

    form = BROperatorEditForm(obj=operator)

    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(operator)
            if populate_fields(form, operator):
                db.session.add(operator)
                db.session.commit()
                return redirect(url_for('.br_operators', office_id=office.id))
        flash_errors(form)
    else:
        if operator.user_id:
            form.user_email.data = operator.user.email

    return render_template('admin/bladerunner/operator_edit.html', operator=operator, form=form, office=office)


@mod.route('/bladerunner/operators/<int:operator_id>/delete', methods=('POST', ))
@roles_required('br.super')
def br_operator_delete(operator_id):
    """
    Удалить офис
    """
    operator = BROperator.query.get_or_404(operator_id)
    db.session.delete(operator)
    db.session.commit()

    return redirect(url_for('.br_operators', office_id=operator.office_id))


