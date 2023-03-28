import datetime
import random
import re

from flask import render_template, redirect, request, url_for, flash, current_app, abort, jsonify, g
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from visual.core import db
from visual.util import flash_errors
from visual.models import User, TeamMember, Department, TeamMemberPhotoQueue, City, TeamMemberStatus, Country

from .. import mod, roles_required
from .forms import TeamMemberForm, TeamFiltersForm, TeamUserForm, TeamStatusesForm


@mod.route('/team/')
@mod.route('/team/department/<int:department_id>')
def team(department_id=None):
    departments = Department.query.order_by(Department.title).all()
    filters = TeamFiltersForm(request.args)
    query = db.session.query(User).join(TeamMember)
    query = query.options(db.joinedload(User.team_status),
                          db.joinedload(User.team_member).options(db.joinedload(TeamMember.department),
                                                                  db.joinedload(TeamMember.city).joinedload(
                                                                      City.country)))
    if request.args.get('fired'):
        query = query.filter(TeamMember.fired != None)
    else:
        query = query.filter(TeamMember.fired == None)

    if department_id:
        query = query.filter(TeamMember.department_id == department_id)

    # Поиск
    if filters.search.data:
        like = '%' + filters.search.data.lower() + '%'
        query = query.filter(
            db.or_(
                db.func.lower(User.name).like(like),
                db.func.lower(User.email).like(like)
            )
        )

    # Сортировка
    sorts = {
        'created': [User.created],
        'name': [User.name],
        'position': [TeamMember.position],
        'last_active': [User.last_active.desc().nullslast(), User.name],
        'age': [TeamMember.birthdate.nullslast(), User.name],
    }
    if request.args.get('fired'):
        sorts['expirience'] = [(TeamMember.fired - TeamMember.hired).desc()]
    else:
        sorts['expirience'] = [(db.func.now() - TeamMember.hired).desc()]
    query = query.order_by(*sorts.get(filters.sort.data, [User.created]))

    users = query.paginate(per_page=50, error_out=False)

    if current_user.has_role('team'):
        photo_queue = db.session.query(db.func.count(TeamMemberPhotoQueue.id)).scalar()
    else:
        photo_queue = None

    # Средний день рожденья сотрудников департамента
    query = db.session.query(
        db.func.cast(db.func.to_timestamp(db.func.avg(db.func.extract('epoch', TeamMember.birthdate))), db.Date)) \
        .select_from(TeamMember)
    if request.args.get('fired'):
        if request.args.get('fired'):
            query = query.filter(TeamMember.fired != None)
        else:
            query = query.filter(TeamMember.fired == None)
    if department_id:
        query = query.filter(TeamMember.department_id == department_id)
    mid_birthdate = query.scalar()
    return render_template('admin/team/index.html', departments=departments, department_id=department_id, users=users,
                           filters=filters, photo_queue=photo_queue,
                           mid_birthdate=mid_birthdate, date_now=datetime.date.today())


@roles_required('team')
@mod.route('/team/<int:user_id>/', methods=['GET'])
def team_profile(user_id):
    user = User.query.options(db.joinedload(User.team_member).joinedload(TeamMember.department)).get_or_404(user_id)

    team_status = TeamMemberStatus.query.filter(TeamMemberStatus.user_id == user.id).order_by(
        TeamMemberStatus.start.desc(), TeamMemberStatus.finish.desc())

    return render_template('admin/team/profile.html', user=user, ROLES=TeamMember.ROLES,
                           date_now=datetime.date.today(),
                           team_status=team_status)


@mod.route('/team/new/', methods=['GET', 'POST'])
@mod.route('/team/<int:user_id>/edit/', methods=['GET', 'POST'])
@roles_required('team')
def team_edit(user_id=None):
    TIMEZONES = current_app.config['TIMEZONES']
    if user_id:
        user = User.query.options(db.joinedload(User.team_member)).get_or_404(user_id)
        if not user.team_member.can_edit():
            abort(403, 'Редактировать сотрудников могут только руководители отделов.')
        form_user = TeamUserForm(obj=user)
        form_member = TeamMemberForm(obj=user.team_member)
    else:
        user = User(created_by=current_user.id, email_confirmed=True)

        user.team_member = TeamMember(department_id=current_user.team_member.department_id)

        form_user = TeamUserForm(obj=user)
        form_member = TeamMemberForm(obj=user.team_member)

    # Создавать сотрудников в любом отделе и перемещать их между отделами может только суперпользователь
    if current_user.has_role('team'):
        form_member.department_id.choices = [(0, '')] + [(int(d.id), d.title) for d in
                                                         Department.query.order_by(Department.title).all()]

        form_member.city_id.choices = [(0, '')]  # + cities
    else:
        del form_member.department_id

    timezones = [('', ''),]
    for code, title in TIMEZONES.items():
        timezones.append((code, title[g.lang]))

    form_member.timezone.choices = timezones

    # Суперпользователей может создавать только суперпользователь
    roles = TeamMember.ROLES.copy()
    if not current_user.has_role('super'):
        del roles['super']
    form_member.roles.choices = list(roles.items())

    if request.method == 'POST':
        if form_user.validate_on_submit() and form_member.validate_on_submit():
            email_namesake = User.query \
                .filter(db.func.lower(User.email) == form_user.email.data.lower(), User.id != user.id) \
                .first()
            if email_namesake:
                flash(
                    'Пользователь с таким адресом электронной почты уже существует (<a href="%s">%s</a>).' %
                    (url_for('.user_edit', user_id=email_namesake.id), email_namesake.name),
                    'danger'
                )
            else:
                form_user.populate_obj(user)

                if not form_member.city_id.data:
                    form_member.city_id.data = None

                form_member.populate_obj(user.team_member)
                db.session.add(user)
                db.session.flush()

                if form_member.photo_.data:
                    user.team_member.photo = form_member.photo_.data
                    user.team_member.avatar = form_member.photo_.data

                if form_user.password.data != '':
                    user.password_hash = User.hash_password(form_user.password.data)

                db.session.commit()
                return redirect(url_for('.team_profile', user_id=user.id))
        else:
            flash_errors(form_user)
            flash_errors(form_member)
    else:
        if not user.id:
            form_user.password.data = ''.join([random.choice('abvgdezkmnoprstufhz23456789') for _ in range(8)])

    return render_template('admin/team/edit.html', user=user, form_user=form_user,
                           form_member=form_member)


@mod.route('/team/<int:user_id>/delete/', methods=['POST'])
@roles_required('team')
def team_delete(user_id):
    user = User.query.get_or_404(user_id)

    if user.team_member:
        del user.team_member.photo
        del user.team_member.avatar

    try:
        db.session.delete(user)
        db.session.commit()
    except IntegrityError as e:
        flash('Удалить пользователя не удалось, так как у него есть объекты или заказы.', 'danger')

    return redirect(url_for('.team'))


@mod.route('/team/<int:user_id>/photo-upload/', methods=['POST'])
def team_photo_upload(user_id):
    user = User.query.get_or_404(user_id)
    if not user:
        abort(404, 'Пользователь не найден.')
    if not user.team_member:
        flash('Этот пользователь не является членом команды.', 'danger')
        return redirect(url_for('.team'))

    photo = TeamMemberPhotoQueue(user_id=user.id)
    db.session.add(photo)
    db.session.flush()
    photo.photo = request.files.get('photo')
    db.session.commit()

    flash('Ваша фотография отправлена на модерацию.', 'success')

    return redirect(url_for('.team_profile', user_id=user.id))


@mod.route('/team/photo-queue/')
@roles_required('team')
def team_photo_queue():
    queue = TeamMemberPhotoQueue.query.order_by(TeamMemberPhotoQueue.created.desc()).all()
    return render_template('admin/team/photo_queue.html', queue=queue)


@mod.route('/team/photo-queue/moderate/', methods=['POST'])
@roles_required('team')
def team_photo_queue_moderate():
    photo_id = request.form.get('photo_id')
    photo = TeamMemberPhotoQueue.query.get_or_404(photo_id)
    action = request.form.get('action')

    if action == 'accept':
        photo.user.team_member.photo = photo.photo.abs_path
        photo.user.team_member.avatar = photo.photo.abs_path
        del photo.photo
        db.session.delete(photo)
        db.session.commit()
    elif action == 'decline':
        del photo.photo
        db.session.delete(photo)
        db.session.commit()

    return jsonify({})


@mod.route('/team_status/<int:status_id>/delete/', methods=['POST'])
@roles_required('team')
def team_status_delete(status_id):
    team_status = TeamMemberStatus.query.get(status_id)
    user_id = team_status.user.id
    db.session.delete(team_status)
    db.session.commit()
    return redirect(url_for('.team_member_status', user_id=user_id))


@mod.route('/team_status/<int:user_id>', methods=['GET', 'POST'])
@roles_required('team')
def team_member_status(user_id):
    def add_status(user_id, form):
        status = TeamMemberStatus(user_id=user.id)
        form.populate_obj(status)
        db.session.add(status)
        db.session.commit()

    page = request.args.get('page', 1, type=int)
    user = User.query.get_or_404(user_id)
    q = TeamMemberStatus.query.filter(TeamMemberStatus.user_id == user_id).order_by(TeamMemberStatus.start.desc(),
                                                                                    TeamMemberStatus.finish.desc())
    team_status = q.paginate(per_page=20, error_out=False)
    form_team_statuses = TeamStatusesForm(obj=user)

    if request.method == 'POST':
        if form_team_statuses.validate_on_submit():
            if form_team_statuses.finish.data:
                if form_team_statuses.start.data <= form_team_statuses.finish.data:
                    add_status(user_id, form_team_statuses)
                    return redirect(url_for('.team_member_status', user_id=user.id))
                else:
                    flash("Дата начала события должна быть меньше даты окончания события", 'danger')
            else:
                flash("Указано событие с открытой датой. Не забудьте исправить", 'info')
                add_status(user_id, form_team_statuses)
                return redirect(url_for('.team_member_status', user_id=user.id))
        flash_errors(form_team_statuses)
    return render_template('admin/team/status_team.html', user=user, form_team_statuses=form_team_statuses,
                           team_status=team_status)


@mod.route('/team_status/<int:user_id>/add_finish_date', methods=['POST'])
def add_finish_date(user_id):
    user = User.query.get_or_404(user_id)
    item_id = request.args.get('item_id')
    status = db.session.query(TeamMemberStatus).get_or_404(item_id)
    finish_date = request.form.get('finish_date')
    try:
        finish_date = datetime.datetime.strptime(finish_date, '%Y-%m-%d').date()
    except ValueError:
        flash("Неверный формат даты", 'danger')
    else:
        if status.start <= finish_date:
            status.finish = finish_date
            db.session.commit()
        else:
            flash("Дата начала события должна быть меньше даты окончания события", 'danger')

    return redirect(url_for('.team_member_status', user_id=user.id))
