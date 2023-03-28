from flask import request, abort, current_app, url_for
from flask_login import current_user, login_required
from flask_babel import gettext

from visual.core import db
from visual.models import DCProject, DCArea, DCMembership, DCTour, DCTask, DCTaskSeen, DCDrawing, User, Tour, TourSeen
from visual.api3 import mod, api_response
from visual.api3.common import apply_sort_to_query
from . import create_projects_query


def load_project_membership_area(project_id, area_id) -> (DCProject, DCMembership, DCArea):
    q = create_projects_query()\
        .add_columns(DCArea)\
        .join(DCArea)\
        .filter(DCProject.id == project_id, DCArea.id == area_id)
    project, membership, *_, area = q.first_or_404(description=gettext('Project or area not found.'))

    return project, membership, area


@mod.route('/devcon/projects/<int:project_id>/areas/<int:area_id>/tours', methods=('POST', ))
@login_required
def post_devcon_tours(project_id, area_id):
    """
    POST /devcon/projects/<id>/areas/<id>/tours
    Input:
    {
        tour_id: int
    }
    """
    project, membership, area = load_project_membership_area(project_id, area_id)

    if 'admin' not in membership.roles and 'super' not in membership.roles and 'cameraman' not in membership.roles:
        abort(403, gettext('You can not add tours in this project.'))

    tour, seen = db.session.query(Tour, TourSeen)\
        .outerjoin(TourSeen, db.and_(TourSeen.tour_id == Tour.id, TourSeen.user_id == current_user.id))\
        .filter(Tour.id == request.json.get('tour_id'))\
        .first_or_404(gettext('Tour not found.'))
    tour.seen_by_me = seen

    # Нет ли уже такого тура в области?
    existing = DCTour.query.filter_by(area_id=area.id, tour_id=tour.id).first()
    if existing is not None:
        abort(400, gettext('Tour already exists in this area.'))

    dc_tour = DCTour(created_by=current_user.id, area_id=area.id, area=area, tour_id=tour.id, tour=tour)
    db.session.add(dc_tour)
    area.cnt_tours += 1
    db.session.commit()

    return api_response(dc_tour.api_repr())


@mod.route('/devcon/projects/<int:project_id>/areas/<int:area_id>/tours', methods=('GET', ))
@login_required
def get_devcon_tours(project_id, area_id):
    """
    GET /devcon/projects/<id>/areas/<id>/tours
    Query String:
        ?children=1 - с турами у областей-детей
        ?tourfields - свойства туров в ответе (default: id, title, preview, created)
    Output:
    [
        {
            "area_id": int,
            "created": datetime,  // когда добавили тур
            "tour": {
                "id": int,
                "title": str,
                "preview": url,
                "screen": url,
                "player_url": str,
                ...
            },
            // Кто добавил тур в область
            "creator": {
                "id": int,
                "name": str,
            }
        },
        ...
    ]
    """
    project, membership, area = load_project_membership_area(project_id, area_id)

    q = db.session.query(DCTour, TourSeen, db.func.count(DCTaskSeen.time_task)) \
        .options(db.joinedload(DCTour.tour), db.joinedload(DCTour.creator)) \
        .outerjoin(TourSeen, db.and_(TourSeen.tour_id == DCTour.tour_id, TourSeen.user_id == current_user.id)) \
        .outerjoin(DCTask, DCTask.tour_id == DCTour.tour_id) \
        .outerjoin(DCTaskSeen, db.and_(DCTaskSeen.task_id == DCTask.id, DCTaskSeen.user_id == current_user.id)) \
        .group_by(DCTour.tour_id, DCTask.id, DCTour.area_id, TourSeen.tour_id, TourSeen.user_id, db.text('tours_1.id'), db.text('users_1.id'))

    if request.args.get('children') == '1':
        # @todo: потенциальное место для оптимизации: проджойнить с рекурсивным запросом на получение детей области?
        children = area.descendants(with_self=True).all()
        q = q.filter(DCTour.area_id.in_([x.id for x in children]))
    else:
        q = q.filter(DCTour.area_id == area.id)

    result = []
    for dc_tour, seen, cnt_tasks_seen in q.all():
        dc_tour.tour.seen_by_me = seen
        result.append(dc_tour.api_repr(cnt_tasks_seen=cnt_tasks_seen))

    return api_response(result)


@mod.route('/devcon/projects/<int:project_id>/areas/<int:area_id>/tours/<int:tour_id>', methods=('PUT', ))
@login_required
def put_devcon_tour(project_id, area_id, tour_id):
    """
    PUT /devcon/projects/<id>/areas/<id>/tours/<id>
    Input:
    {area_id: int}
    """
    project, membership, area = load_project_membership_area(project_id, area_id)

    if 'admin' not in membership.roles and 'super' not in membership.roles and 'cameraman' not in membership.roles:
        abort(403, gettext('You can not move tours in this project.'))

    dc_tour, seen = db.session.query(DCTour, TourSeen)\
        .filter(DCTour.area_id == area.id, DCTour.tour_id == tour_id)\
        .outerjoin(TourSeen, db.and_(TourSeen.tour_id == DCTour.tour_id, TourSeen.user_id == current_user.id))\
        .first_or_404(gettext('Tour not found in this area.'))

    if 'area_id' in request.json:
        new_area = DCArea.query.filter_by(project_id=project.id, id=request.json.get('area_id')).first_or_404(gettext('Target area not found.'))

        # Нет ли уже такого тура в области?
        existing = DCTour.query.filter_by(area_id=new_area.id, tour_id=tour_id).first()
        if existing is not None:
            abort(400, gettext('Tour already exists in this area.'))

        dc_tour.area_id = new_area.id
        area.cnt_tours -= 1
        new_area.cnt_tours += 1

    db.session.commit()

    # После коммита tour.seen_by_me обратится в None
    dc_tour.tour.seen_by_me = seen

    return api_response(dc_tour.api_repr())


@mod.route('/devcon/projects/<int:project_id>/areas/<int:area_id>/tours/<int:tour_id>', methods=('DELETE', ))
@login_required
def delete_devcon_tour(project_id, area_id, tour_id):
    """
    DELETE /devcon/projects/<id>/areas/<id>/tours/<id>
    """
    project, membership, area = load_project_membership_area(project_id, area_id)

    if 'admin' not in membership.roles and 'super' not in membership.roles and 'cameraman' not in membership.roles:
        abort(403, gettext('You can not move tours in this project.'))

    dc_tour = DCTour.query.filter_by(area_id=area.id, tour_id=tour_id).first_or_404(gettext('Tour not found in this area.'))
    db.session.delete(dc_tour)
    area.cnt_tours -= 1
    db.session.commit()

    return '', 204
