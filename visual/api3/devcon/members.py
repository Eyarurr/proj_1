from flask import request, abort, current_app, url_for
from flask_login import current_user, login_required
from flask_babel import gettext

from visual.core import db
from visual.models import DCProject, DCArea, DCMembership, DCTour, DCDrawing, User
from visual.api3 import mod, api_response
from visual.api3.common import apply_sort_to_query
from . import create_projects_query


@mod.route('/devcon/projects/<int:project_id>/members', methods=('POST', ))
@login_required
def post_devcon_members(project_id):
    """
    POST /devcon/projects/<id>/members
    Input:
    {
        email: str,
        roles: [str, ...],
        message: str
    }
    """
    email = request.json.get('email')
    if not email or type(email) is not str or '@' not in email:
        abort(400, gettext('The email address is not valid.'))

    roles = request.json.get('roles')
    if not roles or type(roles) is not list:
        abort(400, gettext('Please choose roles of new member.'))

    for role in roles:
        if role not in DCMembership.ROLES:
            abort(400, gettext('Unknown role "%(role)s"', role=role))
        if role == 'super':
            abort(403, gettext('You can not invite new owner of the project.'))

    project, membership, *_ = create_projects_query([]).filter(DCProject.id == project_id).first_or_404(description=gettext('Project not found.'))

    if 'super' not in membership.roles and 'admin' not in membership.roles:
        abort(403, gettext('You can not invite other users in this project.'))

    user = User.query.filter(User.email == email.strip().lower()).first()
    if user is None:
        abort(400, gettext('User not found.'))

    # Проверяем, нет ли такого юзера уже в списке участников
    existing = DCMembership.query.filter_by(project_id=project.id, user_id=user.id).first()
    if existing:
        existing.roles = roles
    else:
        membership = DCMembership(
            project_id=project.id,
            user_id=user.id,
            roles=roles
        )
        db.session.add(membership)

        user.notify(None, None, 'devcon', 'info',
                    gettext('You have been invited to project "%(project_title)s".', project_title=project.title),
                    url_for('my.devcon', project_id=project.id))
    db.session.commit()

    return '', 204


@mod.route('/devcon/projects/<int:project_id>/members', methods=('GET', ))
@login_required
def get_devcon_members(project_id):
    """
    GET /devcon/projects/<id>/members
    Параметры Query String:
        ?offset
        ?limit
        ?sort: since, name; "-" в начале означает обратную сортировку; default=-since
    Ответ:
    [DCMembership, ...]
    """
    q = create_projects_query().filter(DCProject.id == project_id)
    project, membership, *_ = q.first_or_404(description='Project not found.')

    q = DCMembership.query.filter_by(project_id=project.id).join(User) \
        .options(db.contains_eager(DCMembership.user))

    if membership.roles == ['viewer']:
        abort(403, gettext('You can not view project members.'))

    orders = {
        'since': DCMembership.since,
        'name': User.name
    }
    q = apply_sort_to_query(q, request.args.get('sort', '-since'), orders)

    # Лимит, оффсет
    offset = request.args.get('offset', type=int)
    if offset:
        q = q.offset(offset)
    limit = request.args.get('limit', 500, type=int)
    if limit:
        q = q.limit(limit)

    result = []
    for member in q.all():
        result.append(member.api_repr())

    return api_response(result)


@mod.route('/devcon/projects/<int:project_id>/members/<int:user_id>', methods=('GET', ))
@login_required
def get_devcon_member(project_id, user_id):
    """
    GET /devcon/projects/<id>/members/<id>
    Ответ:
        DCMembership
    """
    q = create_projects_query().filter(DCProject.id == project_id)
    project, membership, *_ = q.first_or_404(description='Project not found.')

    if membership.roles == ['viewer']:
        abort(403, gettext('You can not view project members.'))

    member = DCMembership.query.filter_by(project_id=project.id, user_id=user_id).join(User) \
        .options(db.contains_eager(DCMembership.user)).first()
    if not member:
        abort(404, gettext('Member not found.'))

    return api_response(member.api_repr())


@mod.route('/devcon/projects/<int:project_id>/members/<int:user_id>', methods=('PUT', ))
@login_required
def put_devcon_member(project_id, user_id):
    """
    PUT /devcon/projects/<id>/members/<id>
    Ответ:
        DCMembership
    """
    roles = request.json.get('roles')
    if not roles or type(roles) is not list:
        abort(400, gettext('Please choose roles of new member.'))

    for role in roles:
        if role not in DCMembership.ROLES:
            abort(400, gettext('Unknown role "%(role)s"', role=role))
        if role == 'super':
            abort(403, gettext('You can not assign new owner of the project.'))

    q = create_projects_query().filter(DCProject.id == project_id)
    project, membership, *_ = q.first_or_404(description='Project not found.')

    if 'super' not in membership.roles and 'admin' not in membership.roles:
        abort(403, gettext('You can not modify users in this project.'))

    member = DCMembership.query.filter_by(project_id=project.id, user_id=user_id).join(User) \
        .options(db.contains_eager(DCMembership.user)).first()
    if not member:
        abort(404, gettext('Member not found.'))

    member.roles = roles
    db.session.commit()

    return api_response(member.api_repr())


@mod.route('/devcon/projects/<int:project_id>/members/<int:user_id>', methods=('DELETE', ))
@login_required
def delete_devcon_member(project_id, user_id):
    """
    DELETE /devcon/projects/<id>/members/<id>
    """
    q = create_projects_query().filter(DCProject.id == project_id)
    project, membership, *_ = q.first_or_404(description='Project not found.')

    if not (user_id == current_user.id or 'super' in membership.roles):
        abort(403, gettext("You can not kick users from this project."))

    member = DCMembership.query.filter_by(project_id=project.id, user_id=user_id).join(User) \
        .options(db.contains_eager(DCMembership.user)).first()
    if not member:
        abort(404, gettext('Member not found.'))

    db.session.delete(member)
    db.session.commit()

    return '', 204
