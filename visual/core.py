import os
import time

from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, current_user
from flask_babel import Babel
from lagring import FlaskLagring
from redis import Redis
from rq import Queue
import orjson


db = SQLAlchemy()

babel = Babel()

csrf = CSRFProtect()

login_manager = LoginManager()

storage = FlaskLagring()

redis = Redis(decode_responses=True)
# RQ не умеет работать с Редисом, у которого включено decode_responses=True. Ладно, сделаем ему отдельный коннекшн.
redis_no_decode = Redis()

# Основная очередь задач. Сейчас туда идёт сборщик туров
queue = Queue(default_timeout='12h', connection=redis_no_decode)

# Задачи быстрые, но слишком медленные для обработки в запросе. Создание зипов туров, копирование туров, удаление больших ассетов
queue_quick = Queue('quick', default_timeout='3h', connection=redis_no_decode)

