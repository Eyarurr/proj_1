import sys
import os
import subprocess
import datetime

from visual.core import redis


class BgJobState:
    """Состояние фоновой задачи.
    Описание https://docs.google.com/document/d/1_0CoJs8jH8PtReuyMCJ2Vi-qSXkWWrp6bnl2bTl7kUU/edit

    started: время начала задачи
    finished: время окончания задачи
    status: статус задачи
    complete: доля готовности [0, 1]
    wtf: что происходит
    """
    EXPIRE_TIME = 60*60*24*7

    def __init__(self, job_type, entity_id, status=None):
        self.job_type = job_type
        self.entity_id = entity_id

        self._started = datetime.datetime.now()
        self._finished = None
        self._status = status
        self._complete = 0.0
        self._wtf = ''

        if status:
            self.flush()

    @property
    def started(self):
        return self._started

    @property
    def finished(self):
        return self._finished

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value
        redis.hset(self._redis_key, 'status', self._status)

    @property
    def complete(self):
        return self._complete
    
    @complete.setter
    def complete(self, value):
        self._complete = value
        redis.hset(self._redis_key, 'complete', self._complete)

    @property
    def wtf(self):
        return self._wtf
    
    @wtf.setter
    def wtf(self, value):
        self._wtf = value
        redis.hset(self._redis_key, 'wtf', self._wtf)
    
    def error(self, message):
        """Переводится в статус 'error'"""
        self._status = 'error'
        self._finished = datetime.datetime.now()
        self._wtf = message
        self.flush()

    def done(self, message=''):
        """Переводится в статус 'done'"""
        self._status = 'done'
        self._finished = datetime.datetime.now()
        self._complete = 1
        self._wtf = message
        self.flush()

    @property
    def _redis_key(self):
        return 'jobs:{}.{}'.format(self.job_type, self.entity_id)

    def flush(self):
        """Записывает себя в Redis"""
        data = {
            'started': self._started.isoformat(),
            'status': self.status,
            'complete': self.complete,
            'wtf': self.wtf
        }
        if self._finished:
            data['finished'] = self._finished.isoformat()
        else:
            redis.hdel(self._redis_key, 'finished')

        redis.hmset(self._redis_key, data)
        redis.expire(self._redis_key, self.EXPIRE_TIME)

    @classmethod
    def load(cls, job_type, entity_id):
        """Загружает себя из Redis, если находит. Если не находит, возвращает None"""
        state = cls(job_type, entity_id)
        data = {k: v for k, v in redis.hgetall(state._redis_key).items()}
        if not data:
            return None

        state._started = datetime.datetime.strptime(data['started'], '%Y-%m-%dT%H:%M:%S.%f')
        if b'finished' in data:
            state._finished = datetime.datetime.strptime(data['finished'], '%Y-%m-%dT%H:%M:%S.%f')
        state._status = data.get('status', '')
        state._wtf = data.get('wtf', '')
        state._complete = float(data.get('complete', '0.0'))

        return state

    def __str__(self):
        return '<BgJobState {}/{} {} - {}>'.format(self.job_type, self.entity_id, self.status, self.wtf)
