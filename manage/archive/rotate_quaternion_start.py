from flask_script import Command, Option
from sqlalchemy.orm.attributes import flag_modified

from visual.models import Tour
from visual.util import Quaternion
from visual.core import db


class RotateQuaternionStart(Command):
    """Поворачивает у всех туров кватернионы стартовой точки, в маршрутах и встречающихся в метаданных URLах"""
    option_list = (
        Option('--reverse', '-r', action='store_true', help='Режим обратного поворота'),
    )

    def run(self, reverse):
        def quaternion_rotate(quaternion):
            reverse_quaternion = Quaternion(quaternion[0], -quaternion[2], quaternion[1], quaternion[3])
            if reverse:
                current_quaternion = (Quaternion(0, 1, 0, 0)*reverse_quaternion).as_list()
            else:
                current_quaternion = (reverse_quaternion * Quaternion(0, -1, 0, 0)).as_list()
            new_quaternion = [current_quaternion[0], current_quaternion[2], -current_quaternion[1], current_quaternion[3]]

            if not reverse:
                if new_quaternion == [0, 0, 0, -1]:
                    return [0, 0, 4.0901209104049485e-06, -1]
                elif new_quaternion == [0, 0, 1, 0]:
                    return [0, 0, 1, 4.0901209104049485e-06]
            return new_quaternion

        def text_quaternion_rotate(url):
            if '/#' in url and '/tour/' in url:
                try:
                    base, quaternion = url.split('/#')
                    skybox, x, y, z, w = quaternion.split('_')
                    new_quaternion = '_'.join([skybox, x, y, w, str(-1*int(z))])
                    return '{}/#{}'.format(base, new_quaternion)
                except ValueError:
                    pass
            return url

        def rotate_quaternion(data):
            if isinstance(data, dict):
                if 'url' in data:
                    data['url'] = text_quaternion_rotate(data['url'])
                elif data.get('type') == 'goto':
                    data['q'] = quaternion_rotate(data['q'])
                else:
                    rotate_quaternion(list(data.values()))
            elif isinstance(data, list):
                for value in data:
                    rotate_quaternion(value)

        # @note: Саня, назвать в одном скоупе две функции quaternion_rotate() и rotate_quaternion() — это гениально!

        for tour in Tour.query.all():
            if 'walk' in tour.meta:
                tour.meta['walk'][0]['q'] = quaternion_rotate(tour.meta['walk'][0]['q'])
            if 'start' in tour.meta:
                tour.meta['start']['q'] = quaternion_rotate(tour.meta['start']['q'])
            rotate_quaternion(tour.meta)
            flag_modified(tour, 'meta')
        db.session.commit()
