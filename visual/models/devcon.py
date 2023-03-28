import datetime
import os

from flask import abort
from flask_login import current_user
from flask_babel import gettext
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
import filetype

from lagring import Asset
from lagring.assets.image import ImageAsset
from flask import url_for

from visual.core import db, storage
from visual.models import User

VALIDATION_EXCEPTIONS = (ValueError, KeyError, TypeError, AssertionError, IndexError)


class DCProject(db.Model, storage.Entity):
    """
    Проект.
    """
    __tablename__ = 'dc_projects'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False, default='', server_default='')
    details = db.Column(JSONB, nullable=False, default={}, server_default='{}')

    icon = ImageAsset(width=256, height=256, transform='crop')

    user = db.relationship('User')
    members = db.relationship('DCMembership', cascade='save-update, merge, delete, delete-orphan')

    def api_repr(self, **kwargs):
        d = {
            **{
                'id': self.id,
                'created': self.created,
                'title': self.title,
                'details': self.details,
                'icon': None if self.icon is None else self.icon.url,
                'user': {
                    'id': self.user_id,
                    'name': self.user.name
                }
            },
            **kwargs
        }

        return d

    @staticmethod
    def subquery_cnt_areas():
        return db.session \
            .query(DCArea.project_id, db.func.count(DCArea.id).label('cnt_areas')) \
            .group_by(DCArea.project_id) \
            .subquery()

    @staticmethod
    def subquery_cnt_members():
        return db.session \
            .query(DCMembership.project_id, db.func.count(DCMembership.user_id).label('cnt_members')) \
            .group_by(DCMembership.project_id) \
            .subquery()

    @staticmethod
    def subquery_cnt_tours():
        return db.session \
            .query(DCArea.project_id, db.func.count(DCTour.tour_id).label('cnt_tours')) \
            .join(DCArea) \
            .group_by(DCArea.project_id) \
            .subquery()


class DCMembership(db.Model):
    """Членство юзера в проекте."""
    __tablename__ = 'dc_members'

    ROLES = ('super', 'admin', 'cameraman', 'plotman', 'viewer', 'taskman', 'worker')

    project_id = db.Column(db.Integer, db.ForeignKey('dc_projects.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, primary_key=True, index=True)
    since = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    roles = db.Column(ARRAY(db.String(32), zero_indexes=True))

    project = db.relationship('DCProject', back_populates='members')
    user = db.relationship('User')

    def has_role(self, *args):
        """Возвращает True, если хоть одна роль из *args есть в списке ролей пользователя.
        Для owner'а всегда возвращает True."""
        if 'super' in self.roles:
            return True

        for role in args:
            if role in self.roles:
                return True

        return False

    def api_repr(self, **kwargs):
        d = {
            **{
                'project_id': self.project_id,
                'since': self.since,
                'roles': self.roles,
                'user': {
                    'id': self.user_id,
                    'name': self.user.name
                }
            },
            **kwargs
        }
        return d


class DCArea(db.Model):
    """Область."""
    __tablename__ = 'dc_areas'

    id = db.Column(db.Integer(), primary_key=True)
    project_id = db.Column(db.Integer(), db.ForeignKey('dc_projects.id', ondelete='CASCADE', onupdate='CASCADE'), index=True)
    parent_id = db.Column(db.Integer(), db.ForeignKey('dc_areas.id', ondelete='CASCADE', onupdate='CASCADE'), index=True)
    sort = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    title = db.Column(db.String(255), nullable=False, default='', server_default='')
    cnt_tours = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    cnt_drawings = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    cnt_tasks = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    # Непосредственные дети
    children = db.relationship('DCArea', backref=db.backref('parent', remote_side=id))
    creator = db.relationship('User', foreign_keys=[created_by])

    def api_repr(self, **kwargs):
        d = {
            **{
                'id': self.id,
                'parent_id': self.parent_id,
                'project_id': self.project_id,
                'created': self.created,
                'sort': self.sort,
                'title': self.title,
                'cnt_tours': self.cnt_tours,
                'cnt_drawings': self.cnt_drawings,
                'cnt_tasks': self.cnt_tasks,
                'creator': {
                    'id': self.created_by,
                    'name': self.creator.name
                }
            },
            **kwargs
        }
        return d

    def descendants(self, with_self=False):
        """Возвращает рекурсивную Query на получение всех потомков области (вместе с собой или без, в зависимости от
        `with_self`"""
        if with_self:
            top = DCArea.query.filter_by(id=self.id)
        else:
            top = DCArea.query.filter_by(parent_id=self.id)
        top = top.cte('cte', recursive=True)

        bottom = DCArea.query.join(top, DCArea.parent_id == top.c.id)

        rec = top.union(bottom)

        return db.session.query(rec)


class DCDrawing(db.Model, storage.Entity):
    """Чертёж."""
    __tablename__ = 'dc_drawings'

    id = db.Column(db.Integer(), primary_key=True)
    area_id = db.Column(db.Integer(), db.ForeignKey('dc_areas.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    title = db.Column(db.String(255))

    area = db.relationship('DCArea', backref=db.backref('drawings'))
    creator = db.relationship('User', foreign_keys=[created_by])

    file = Asset()
    icon = ImageAsset(width=512, height=512, transform='crop')

    def api_repr(self, **kwargs):
        d = {
            **{
                'id': self.id,
                'area_id': self.area_id,
                'created': self.created,
                'creator': {
                    'id': self.created_by,
                    'name': self.creator.name
                },
                'title': self.title,
                'file': self.file.url if self.file else None
            },
            **kwargs
        }
        return d


class DCTour(db.Model):
    """Привязка тура к области."""
    __tablename__ = 'dc_tours'

    area_id = db.Column(db.Integer(), db.ForeignKey('dc_areas.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, primary_key=True)
    tour_id = db.Column(db.Integer(), db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    cnt_tasks = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    area = db.relationship('DCArea', backref=db.backref('tours', cascade='save-update, merge, delete, delete-orphan'))
    tour = db.relationship('Tour', backref=db.backref('areas', cascade='save-update, merge, delete, delete-orphan'))
    creator = db.relationship('User', foreign_keys=[created_by])

    def api_repr(self, **kwargs):
        d = {
            **{
                'area_id': self.area_id,
                'created': self.created,
                'creator': {
                    'id': self.created_by,
                    'name': self.creator.name
                },
                'cnt_tasks': self.cnt_tasks,
                'tour': {
                    'id': self.tour.id,
                    'title': self.tour.title,
                    'preview': None if not self.tour.preview else self.tour.preview.url,
                    'screen': None if not self.tour.preview else self.tour.screen.url,
                    'created': self.tour.created,
                    'player_url': url_for('front.tour', tour_id=self.tour.id),
                    'seen_by_me': self.tour.seen_by_me.seen if self.tour.seen_by_me else None
                }
            },
            **kwargs
        }
        return d


class DCTask(db.Model):
    """Задача."""
    __tablename__ = 'dc_tasks'

    STATUSES = ('draft', 'todo', 'progress', 'review', 'debug', 'pause', 'done', 'canceled', 'archive')

    id = db.Column(db.Integer(), primary_key=True)
    area_id = db.Column(db.Integer(), db.ForeignKey('dc_areas.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=True, index=True)
    tour_id = db.Column(db.Integer(), db.ForeignKey('tours.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    updated = db.Column(db.DateTime(timezone=True))
    status = db.Column(db.Enum(*STATUSES, name='dc_task_status'), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=True)

    title = db.Column(db.String(1024), nullable=False)
    description = db.Column(db.String(1024))
    priority = db.Column(db.SmallInteger)
    deadline = db.Column(db.DateTime(timezone=True))
    tour_pos = db.Column(ARRAY(db.Float, zero_indexes=True))
    tour_render_props = db.Column(JSONB)

    cnt_files = db.Column(db.Integer, default=0, server_default='0', nullable=False)
    cnt_comments = db.Column(db.Integer, default=0, server_default='0', nullable=False)

    area = db.relationship('DCArea', backref=db.backref('tasks', cascade='save-update, merge, delete, delete-orphan'))
    creator = db.relationship('User', foreign_keys=[created_by])
    assignee = db.relationship('User', foreign_keys=[assigned_to])

    def api_repr(self, **kwargs):
        d = {
            **{
                'id': self.id,
                'area_id': self.area_id,
                'tour_id': self.tour_id,
                'created': self.created,
                'creator': {
                    'id': self.created_by,
                    'name': self.creator.name
                },
                'updated': self.updated,
                'status': self.status,
                'assignee': None if self.assigned_to is None else {
                    'id': self.assigned_to,
                    'name': self.assignee.name
                },
                'title': self.title,
                'description': self.description,
                'priority': self.priority,
                'deadline': self.deadline,
                'tour_pos': self.tour_pos,
                'tour_render_props': self.tour_render_props,
                'cnt_files': self.cnt_files,
                'cnt_comments': self.cnt_comments
            },
            **kwargs
        }
        return d

    @classmethod
    def seen_props(cls, seen):
        """Возвращает словарь с ключами time_task_seen, time_files_seen, cnt_files_seen, time_comments_seen, cnt_comments_seen,
        нужные для ответов API с классом DCTask. Понимает, когда seen=None"""
        res = {}
        if seen:
            res['time_task_seen'] = seen.time_task
            res['cnt_files_seen'] = seen.cnt_files
            res['time_files_seen'] = seen.time_files
            res['cnt_comments_seen'] = seen.cnt_comments
            res['time_comments_seen'] = seen.time_comments
        else:
            res['time_task_seen'] = None
            res['cnt_files_seen'] = 0
            res['time_files_seen'] = None
            res['cnt_comments_seen'] = 0
            res['time_comments_seen'] = None
        return res

    def update_from_api_request(self, payload):
        """
        Обновляет свои свойства из тела запроса API в `payload`. Проверяет их на валидность и выбрасывает
        abort(400). Нуждается у установленной реляции self.area.
        :param payload: dict {status, assignee {id}, title, description, priority, deadline}
        :return:
        """
        changed = {}

        if 'status' in payload:
            try:
                status = str(payload['status'])
                assert status in self.STATUSES
            except VALIDATION_EXCEPTIONS:
                return abort(400, gettext('Bad task status.'))
            if self.status != status:
                changed['status'] = {'was': self.status, 'now': status}
                self.status = status

        if 'tour_id' in payload:
            # Проверяем, что этот тур привязан к этой области
            if payload['tour_id'] is None:
                self.tour_id = None
            else:
                try:
                    tour_id = int(payload['tour_id'])
                except VALIDATION_EXCEPTIONS:
                    return abort(400, gettext('Malformed %(key)s value.', key='tour_id'))
                with db.session.no_autoflush:
                    dc_tour = DCTour.query.filter_by(tour_id=tour_id, area_id=self.area_id).first()
                if dc_tour is None:
                    return abort(400, gettext('Tour is not attached to area.'))
                self.tour_id = tour_id

        if 'tour_pos' in payload:
            if payload['tour_pos'] is None:
                self.tour_pos = None
            else:
                try:
                    assert len(payload['tour_pos']) == 3
                    self.tour_pos = [float(x) for x in payload['tour_pos']]
                except VALIDATION_EXCEPTIONS:
                    return abort(400, gettext('Malformed %(key)s value.', key='tour_pos'))

        if 'tour_render_props' in payload:
            if payload['tour_render_props'] is None:
                self.tour_render_props = None
            else:
                try:
                    assert type(payload['tour_render_props']) is dict
                    self.tour_render_props = payload['tour_render_props']
                except VALIDATION_EXCEPTIONS:
                    return abort(400, gettext('Malformed %(key)s value.', key='tour_render_props'))

        if 'assignee' in payload:
            if payload['assignee'] is None:
                if self.assigned_to is not None:
                    changed['assignee'] = {'was': None if self.assigned_to is None else {'id': self.assigned_to, 'name': self.assignee.name}, 'now': None}
                self.assigned_to = None
            else:
                try:
                    assigned_to = int(payload['assignee']['id'])
                except VALIDATION_EXCEPTIONS:
                    return abort(400, gettext('Bad task assignee.'))

                if assigned_to != self.assigned_to:
                    with db.session.no_autoflush:
                        assignee = DCMembership.query.filter_by(project_id=self.area.project_id, user_id=assigned_to)\
                            .options(db.joinedload(DCMembership.user))\
                            .first()
                    if assignee is None:
                        return abort(400, gettext('Assigned user is not a member of this project.'))
                    if not assignee.has_role('worker', 'taskman', 'admin'):
                        return abort(400, gettext('You can not assign tasks to that user.'))

                    changed['assignee'] = {
                        'was': None if self.assigned_to is None else {'id': self.assigned_to, 'name': self.assignee.name},
                        'now': {'id': assignee.user_id, 'name': assignee.user.name}
                    }

                    self.assigned_to = assignee.user_id
                    self.assignee = assignee.user

        if 'title' in payload:
            try:
                assert payload['title'] is not None
                title = str(payload['title']).strip()
                assert title != ''
            except VALIDATION_EXCEPTIONS:
                return abort(400, gettext('Bad task title.'))
            if self.title != title:
                changed['title'] = {'was': self.title, 'now': title}
                self.title = title

        if 'description' in payload:
            if payload['description'] is None:
                description = None
            else:
                try:
                    description = str(payload['description']).strip()
                except VALIDATION_EXCEPTIONS:
                    return abort(400, gettext('Bad task description.'))
            if self.description != description:
                changed['description'] = {'was': self.description, 'now': description}
                self.description = description

        if 'priority' in payload:
            if payload['priority'] is None:
                priority = None
            else:
                try:
                    priority = int(payload['priority'])
                    assert -32000 < priority < 32000
                except VALIDATION_EXCEPTIONS:
                    return abort(400, gettext('Bad task priority.'))
            if self.priority != priority:
                changed['priority'] = {'was': self.priority, 'now': priority}
                self.priority = priority

        if 'deadline' in payload:
            if payload['deadline'] is None:
                deadline = None
            else:
                try:
                    deadline = datetime.datetime.fromisoformat(payload['deadline'])
                except VALIDATION_EXCEPTIONS:
                    return abort(400, gettext('Bad task deadline.'))
            if self.deadline != deadline:
                changed['deadline'] = {'was': None if self.deadline is None else self.deadline.isoformat(),
                                       'now': None if deadline is None else deadline.isoformat()}
                self.deadline = deadline

        if self.tour_pos is not None and self.tour_id is None:
            return abort(400, 'Task has 3D-coordinate, but is not attached to tour.')

        return changed

    def add_comment(self, type_, content):
        """Добавляет к задаче комментарий типа `type_` и содержимого `conent`"""
        comment = DCTaskComment(
            created_by=current_user.id,
            task=self,
            task_id=self.id,
            type=type_,
            content=content
        )
        db.session.add(comment)
        self.cnt_comments += 1


class DCTaskSeen(db.Model):
    """Сведения о просмотре задач и их частей разными юзерами."""
    __tablename__ = 'dc_task_seen'

    task_id = db.Column(db.Integer, db.ForeignKey('dc_tasks.id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True)

    # Когда юзер видел задачу вообще
    time_task = db.Column(db.DateTime(timezone=True))

    # Когда юзер видел аттачи
    time_files = db.Column(db.DateTime(timezone=True))
    # ...и сколько их было в момент time_files
    cnt_files = db.Column(db.Integer, default=0, server_default='0')
    # Когда юзер видел комменты
    time_comments = db.Column(db.DateTime(timezone=True))
    # ...и сколько их было в момент time_comments
    cnt_comments = db.Column(db.Integer, default=0, server_default='0')


class DCTaskFile(db.Model, storage.Entity):
    """Аттач к задаче."""
    __tablename__ = 'dc_task_files'

    id = db.Column(db.Integer(), primary_key=True)
    task_id = db.Column(db.Integer(), db.ForeignKey('dc_tasks.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=True, index=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    title = db.Column(db.String(1024))

    file = Asset()
    # Согласно https://datatracker.ietf.org/doc/html/rfc4288#section-4.2, mimetype может содержать до 127*2+1=255 символов
    file_type = db.Column(db.String(255))
    file_size = db.Column(db.Integer)
    file_name = db.Column(db.String(255))
    # Для картинок тут будет её уменьшенная копия, для видео — скриншот первого кадра.
    preview = ImageAsset(width=512, height=512, transform='crop')

    task = db.relationship('DCTask', backref=db.backref('files', cascade='save-update, merge, delete, delete-orphan'))
    creator = db.relationship('User', foreign_keys=[created_by])

    def api_repr(self, **kwargs):
        d = {
            **{
                'id': self.id,
                'task_id': self.task_id,
                'created': self.created,
                'creator': {
                    'id': self.created_by,
                    'name': self.creator.name
                },
                'title': self.title,
                'file': None if not self.file else {
                    # @todo: тут могут сгенериться ленивые запросы к self.task.area!
                    'url': url_for('api3.download_devcon_tasks_file', project_id=self.task.area.project_id, task_id=self.task_id, file_id=self.id),
                    'type': self.file_type,
                    'size': self.file_size,
                    'name': self.file_name
                },
                'preview': None if not self.preview else self.preview.url
            },
            **kwargs
        }
        return d

    def update_from_api_request(self, payload):
        """
        Обновляет свои свойства из тела запроса API в `payload`. Проверяет их на валидность и выбрасывает
        abort(400).
        :param payload: dict {file, title}
        :return:
        """
        from visual.api3.common import handle_asset_param
        if 'file' not in payload:
            return abort(400, gettext('You should upload file.'))

        try:
            with handle_asset_param(payload['file'], 'file') as (fh, filename, *_):
                self.file = fh
                self.file_name = os.path.basename(filename)
        except ValueError as e:
            abort(400, str(e))

        self.file_size = os.stat(self.file.abs_path).st_size
        kind = filetype.guess(self.file.abs_path)
        if kind is not None:
            self.file_type = kind.mime
            if kind.mime.startswith('image/'):
                self.preview = self.file.abs_path

        if 'title' in payload:
            try:
                if payload['title'] is None:
                    self.title = None
                else:
                    self.title = str(payload['title']).strip()
            except VALIDATION_EXCEPTIONS:
                return abort(400, gettext('Bad file title.'))


class DCTaskComment(db.Model):
    """Коммент к задаче."""
    __tablename__ = 'dc_task_comments'

    TYPES = ('message', 'task.created', 'task.changed', 'files.created', 'files.deleted')

    id = db.Column(db.Integer(), primary_key=True)
    task_id = db.Column(db.Integer(), db.ForeignKey('dc_tasks.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=True)

    type = db.Column(db.Enum(*TYPES, name='dc_task_comment_type'), nullable=False)
    content = db.Column(JSONB)

    task = db.relationship('DCTask', backref=db.backref('comments', cascade='save-update, merge, delete, delete-orphan'))
    creator = db.relationship('User', foreign_keys=[created_by])

    def api_repr(self, **kwargs):
        d = {
            **{
                'id': self.id,
                'task_id': self.task_id,
                'created': self.created,
                'creator': {
                    'id': self.created_by,
                    'name': self.creator.name
                },
                'type': self.type,
                'content': self.content
            },
            **kwargs
        }
        return d

    def update_from_api_request(self, payload):
        """
        Обновляет свои свойства из тела запроса API в `payload`. Проверяет их на валидность и выбрасывает
        abort(400). Устанавливает self.type в 'message', заполняет self.content согласно спеке.
        :param payload: dict {text}
        :return:
        """
        try:
            assert payload['text'] is not None
            text = str(payload['text']).strip()
            assert text
        except VALIDATION_EXCEPTIONS:
            return abort(400, gettext('Please enter your comment text.'))

        self.type = 'message'
        self.content = {'text': text}
