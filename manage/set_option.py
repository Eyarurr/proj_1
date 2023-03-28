from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import or_

from visual.models import Tour
from visual.core import db


class SetOption:
    """Массовая установка опций в турах"""
    def run(self, tours, users, options):
        tours = list(map(int, tours.split(','))) if tours is not None else []
        users = list(map(int, users.split(','))) if users is not None else []

        for tour in Tour.query.filter(or_(Tour.id.in_(tours), Tour.user_id.in_(users))).all():
            for option in options:
                key = option.split('=')[0]
                value = option.split('=')[1]
                try:
                    value = eval(value)
                except NameError:
                    print('Тур# {} опция {} установлена как тип string'.format(tour.id, key))
                tour.meta.setdefault('options', {})[key] = value
            flag_modified(tour, 'meta')
        db.session.commit()
