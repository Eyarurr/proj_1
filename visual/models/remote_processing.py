import datetime

from sqlalchemy.dialects.postgresql import JSONB
from flask import abort

from visual.core import db


class RemoteDataset(db.Model):
    __tablename__ = 'remote_datasets'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(16), nullable=False)
    remote_id = db.Column(db.String(32), nullable=False)
    last_event_id = db.Column(db.Integer, db.ForeignKey('remote_events.id', onupdate='CASCADE', ondelete='SET NULL', name='remote_datasets_last_event_id_fkey'), nullable=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    title = db.Column(db.String)
    props = db.Column(JSONB, nullable=True)

    user = db.relationship('User')
    last_event = db.relationship('RemoteEvent', foreign_keys=[last_event_id])

    def send_event(self, event=None, **kwargs):
        """Отправляет в датасет евент `event` или новый, инициализируемый параметрами этого метода."""
        if event is None:
            event = RemoteEvent(dataset_id = self.id, **kwargs)
        db.session.add(event)
        db.session.flush()
        self.last_event_id = event.id
        self.last_event = event
        db.session.commit()

    def api_repr(self):
        """Возвращает своё представление для ответа API."""
        d = {
            'type': self.type,
            'id': self.remote_id,
            'created': self.created.isoformat(),
            'user_id': self.user_id,
            'title': self.title,
            'props': self.props
        }
        if self.last_event is None:
            d['last_event'] = None
        else:
            d['last_event'] = self.last_event.api_repr()
        return d

    def update_from_api_request(self, rq):
        """Обновляет свойства объекта из тела запроса API в `rq`. Выбрасывает HTTP 400, если там ошибки."""
        if 'title' in rq:
            if type(rq['title']) is not str or len(rq['title']) > 1024:
                abort(400, 'Bad Dataset.title value. Should be string shorter than 1 kB.')
            self.title = rq['title']

        if 'props' in rq:
            if type(rq['props']) is not dict:
                abort(400, 'Bad Dataset.props value. Should be object.')
            self.props = rq['props']


class RemoteEvent(db.Model):
    __tablename__ = 'remote_events'

    id = db.Column(db.Integer, primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    dataset_id = db.Column(db.Integer, db.ForeignKey('remote_datasets.id', ondelete='CASCADE', onupdate='CASCADE'), index=True)
    type = db.Column(db.String(64), nullable=False)
    job_id = db.Column(db.String)
    ts = db.Column(db.DateTime(timezone=True))
    meta = db.Column(JSONB, nullable=True)

    def api_repr(self):
        """Возвращает своё представление для ответа API."""
        d = {
            'type': self.type,
            'job_id': self.job_id,
            'meta': self.meta
        }
        if self.ts:
            d['ts'] = self.ts.isoformat()
        else:
            d['ts'] = self.created.isoformat()
        return d

    def update_from_api_request(self, rq):
        """Обновляет свойства объекта из тела запроса API в `rq`. Выбрасывает HTTP 400, если там ошибки."""
        if 'type' not in rq or type(rq['type']) is not str or len(rq['type']) > RemoteEvent.type.type.length:
            abort(400, 'Bad Event.type value. Should be sting shorter than {} bytes.'.format(RemoteEvent.type.type.length))
        self.type = rq['type']

        if 'job_id' in rq:
            if rq['job_id'] is not None and (type(rq['job_id']) is not str or len(rq['job_id']) > 128):
                abort(400, 'Bad Event.job_id value. Should be string shorted than 128 bytes.')
            self.job_id = rq['job_id']

        if 'ts' in rq:
            try:
                self.ts = datetime.datetime.fromisoformat(rq['ts'])
            except (TypeError, ValueError):
                abort(400, 'Bad Event.ts value. Should be ISO 8601 datetime string.')

        if 'meta' in rq:
            if type(rq['meta']) is not dict:
                abort(400, 'Bad Event.meta value. Should be an object.')
            self.meta = rq['meta']
