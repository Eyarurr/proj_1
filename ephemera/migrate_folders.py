# Убирает из TourSkybox.title весь HTML

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from sqlalchemy.orm.attributes import flag_modified
from visual import create_app
from visual.core import db
from visual.models import User, Estate, Tour, Footage, Folder


app = create_app('config.local.py')


with app.app_context():
    # Стираем все папки
    Folder.query.delete()

    for user in User.query.order_by(User.created).all():
        estates = Estate.query.filter_by(user_id=user.id).all()
        if not estates:
            continue

        print('{:3d} {:50s}'.format(user.id, user.email))
        if len(estates) == 1:
            # У юзера всего один объект
            cnt_tours = db.session.query(db.func.count(Tour.id)).filter(Tour.estate_id == estates[0].id).scalar()
            print('    {:50s}: {}'.format(estates[0].title, cnt_tours))
        else:
            # У юзера несколько объектов
            for estate in estates:
                cnt_tours = db.session.query(db.func.count(Tour.id)).filter(Tour.estate_id == estate.id).scalar()
                folder = Folder(user_id=user.id, title=estate.title)
                db.session.add(folder)
                db.session.flush()
                Tour.query.filter_by(estate_id=estate.id).update({'folder_id': folder.id})

    db.session.commit()
