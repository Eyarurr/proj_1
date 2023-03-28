import uuid

from flask import current_app

from visual.models import User, RemoteDataset, RemoteEvent
from visual.core import db

DATASET_PROPS = [
    {},
    {'cnt_sweeps': 30},
    {'cnt_floors': 3},
    {'cnt_sweeps': 77, 'cnt_floors': 4},
    {'device': {'model': 'V8'}},
    {'device': {'model': 'V8', 'sn': '100500'}},
    {'device': {'model': 'V8', 'nickname': 'Камера Ромуальдыча'}},
    {'device': {'model': 'V8', 'sn': '300400', 'nickname': 'Элегия'}},
    {'device': {'model': 'V8', 'nickname': 'Камера Ромуальдыча'}, 'cnt_sweeps': 50, 'cnt_floors': 2, 'size': 5000000},
]

EVENTS = [
    ('upload.started', {}),
    ('upload.progress', {}),
    ('upload.progress', {'progress': 0.5}),
    ('upload.progress', {'progress': 0.3, 'eta': '2022-11-25T14:46:49.096239+03:00'}),
    ('upload.progress', {'progress': 0.3, 'eta': '2022-12-10T12:00:00', 'message': 'Загрузка в процессе!'}),
    ('upload.paused', {'reason': 'Остановка загрузки, соединение не установлено!'}),
    ('upload.warning', {'warnings': ['Возникли проблемы при загрузке сцены!']}),
    ('upload.success', {'warnings': ['Загрузка прошла успешно!', 'Еще одно сообщение!']}),
    ('upload.failed', {'errors': ['Загрузка сцены не удалась!']}),
    ('processing.started', {}),
    ('processing.progress', {'stage': 'queued'}),
    ('processing.progress', {'stage': 'processing'}),
    ('processing.progress', {}),
    ('processing.paused', {}),
    ('processing.warning', {'warnings': ['Возникли проблемы при обработке сцены!']}),
    ('processing.success', {}),
    ('processing.failed', {'errors': ['Обработка сцены не удалась!']}),
    ('transfer.started', {}),
    ('transfer.progress', {'progress': 0.3, 'eta': '2022-12-10T12:00:00'}),
    ('transfer.paused', {}),
    ('transfer.warning', {'warnings': ['Возникли проблемы при выгрузке!']}),
    ('transfer.success', {'results': [{'entity_type': 'tour', 'entity_id': 65535}]}),
    ('transfer.failed', {'errors': ['Выгрузка сцены не удалась!']}),
]


class GenerateDatasets:
    """Генерит в юзера датасеты с событиями для отладки интерфейса."""
    def run(self, user_email, clear=False):
        user = User.query.filter(db.func.lower(User.email) == user_email.lower()).first()

        if not user:
            current_app.logger.error('Пользователь с почтой "{}" не найден'.format(user_email))
            return

        if clear:
            RemoteDataset.query.filter_by(user_id=user.id).delete()
            db.session.commit()

        for i in range(30):
            dataset = RemoteDataset(
                user_id=user.id, type='filincam', remote_id=uuid.uuid4().hex, title='Сцена {}'.format(i + 1),
                props=DATASET_PROPS[i % len(DATASET_PROPS)]
            )
            db.session.add(dataset)
            db.session.flush()
            edata = EVENTS[i % len(EVENTS)]
            event = RemoteEvent(dataset_id=dataset.id, type=edata[0], meta=edata[1])
            db.session.add(event)
            db.session.flush()
            dataset.last_event_id = event.id
            db.session.commit()
