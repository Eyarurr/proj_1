from flask_login import current_user
from flask_babel import gettext

from visual.core import db
from visual.models import DCProject, DCMembership, DCArea, DCTask


def create_projects_query(fields=None):
    """
    Создаёт запрос для получения информации о проектах с участием текущего юзера и, если есть нужные подстроки в
    `fields`, то со счётчиками областей, членов и туров. Типа
    SELECT p.* FROM dc_projects JOIN dc_members m WHERE m.user_id = current_user.id
    :param fields:
    :return:
    """
    if fields is None:
        fields = []

    q = db.session.query(DCProject, DCMembership).join(DCMembership).filter(DCMembership.user_id == current_user.id)

    if 'cnt_areas' in fields:
        cnt_areas = DCProject.subquery_cnt_areas()
        q = q.add_columns(cnt_areas.c.cnt_areas).outerjoin(cnt_areas, cnt_areas.c.project_id == DCProject.id)
    else:
        q = q.add_columns(db.null())

    if 'cnt_members' in fields:
        cnt_members = DCProject.subquery_cnt_members()
        q = q.add_columns(cnt_members.c.cnt_members).outerjoin(cnt_members, cnt_members.c.project_id == DCProject.id)
    else:
        q = q.add_columns(db.null())

    if 'cnt_tours' in fields:
        cnt_tours = DCProject.subquery_cnt_tours()
        q = q.add_columns(cnt_tours.c.cnt_tours).outerjoin(cnt_tours, cnt_tours.c.project_id == DCProject.id)
    else:
        q = q.add_columns(db.null)

    return q


def load_project_membership(project_id) -> (DCProject, DCMembership):
    """
    Загружает проект и членство в нём текущего юзера
    :param project_id:
    :return:
    """
    q = db.session.query(DCProject, DCMembership) \
        .join(DCMembership, db.and_(DCMembership.project_id == DCProject.id, DCMembership.user_id == current_user.id)) \
        .filter(DCProject.id == project_id)

    project, membership = q.first_or_404(description=gettext('Project not found.'))
    return project, membership


def load_project_membership_area(project_id, area_id) -> (DCProject, DCMembership, DCArea):
    """
    Загружает проект, членство и область
    :param project_id:
    :param area_id:
    :return:
    """
    q = db.session.query(DCProject, DCMembership, DCArea) \
        .join(DCProject, DCProject.id == DCArea.project_id) \
        .join(DCMembership, db.and_(DCMembership.project_id == DCProject.id, DCMembership.user_id == current_user.id)) \
        .filter(DCArea.id == area_id, DCProject.id == project_id)

    project, membership, area = q.first_or_404(description=gettext('Project or area not found.'))
    return project, membership, area


def load_project_membership_area_task(project_id, area_id, task_id) -> (DCProject, DCMembership, DCArea, DCTask):
    """
    Загружает проект, членство и задачу
    :param project_id:
    :param area_id:
    :param task_id:
    :return:
    """
    q = db.session.query(DCTask, DCArea, DCProject, DCMembership) \
        .join(DCArea, DCArea.id == DCTask.area_id) \
        .join(DCProject, DCProject.id == DCArea.project_id) \
        .join(DCMembership, db.and_(DCMembership.project_id == DCProject.id, DCMembership.user_id == current_user.id)) \
        .filter(DCTask.id == task_id, DCProject.id == project_id)
    if area_id:
        q = q.filter(DCArea.id == area_id)

    task, area, project, membership = q.first_or_404(description=gettext('Task not found.'))
    return project, membership, area, task


from . import members, projects, areas, tours, drawings, tasks, task_files, task_comments
