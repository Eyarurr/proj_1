import os
import random
import yaml

from flask_script import Command, Option

from visual.models import User, Estate, Tour, Offer, OfferTour, Footage
from visual.core import db
from .progress import Progress
from . import Recount

progress = Progress()


class ImportVirtual(Command):
    """
    Скрипт для импорта туров с biganto-visual.ru. Первым аргументом получает путь к корню biganto-visual.ru,
    сведения о юзерах, объектах и турах получает из import_virtual.yaml.
    Скрипт идемпонетнтый: юзеров, объекты и туры создаёт, если их нет в базе. Юзеров ищет по e-mail, объекты и туры -
    по названию.
    """
    option_list = (
        Option('virtual_root'),
    )

    def _get_user(self, user_data):
        user = User.query.filter(db.func.lower(User.email) == user_data['email'].lower()).first()

        if not user:
            password = ''.join([random.choice('abvgdezijklmnoprstufhcxy234567890') for _ in range(6)])
            user = User(
                roles=['login'],
                password_hash=User.hash_password(password),
                email=user_data['email'],
                name=user_data.get('name', ''),
                phone=user_data.get('phone'),
                admin_comment=user_data.get('admin_comment')
            )
            db.session.add(user)
            progress.shout('Создан: %s - %s:%s (%s)' % (user.name, user.email, password, user.admin_comment or ''))

        return user

    def _get_estate(self, user, estate_data):
        estate = Estate.query\
            .filter(db.func.lower(Estate.title) == estate_data['title'].lower(), Estate.user_id == user.id)\
            .first()

        if not estate:
            estate = Estate(
                status='complete',
                title=estate_data['title'],
                address=estate_data.get('address'),
                user=user
            )
            db.session.add(estate)
            progress.say('Объект %s: создан' % estate.title)
        else:
            progress.say('Объект %s: найден' % estate.title)

        return estate

    def _get_tour(self, estate, tour_data):
        tour = Tour.query\
            .filter(db.func.lower(Tour.title) == tour_data['title'].lower(), Tour.estate_id == estate.id)\
            .first()

        if not tour:
            footage = Footage(type='virtual')
            db.session.add(footage)
            db.session.flush()
            tour = Tour(
                footage=footage,
                estate=estate,
                hidden=False,
                title=tour_data['title']
            )
            db.session.add(tour)
            progress.say('    Тур %s: создан' % tour.title)
        else:
            progress.say('    Тур %s: найден' % tour.title)

        return tour

    def _get_multitour(self, estate):
        multitour = Offer.query.filter_by(estate_id=estate.id, type='multitour', title=estate.title).first()
        if multitour:
            return False

        multitour = Offer(
            estate=estate,
            type='multitour',
            title=estate.title,
            template='common',
            template_data={'title': estate.title}
        )
        return multitour

    def run(self, virtual_root):
        progress.action('Импортируется контент virtual.biganto.ru из директории %s' % virtual_root)

        scenario = yaml.load(open('manage/import_virtual.yaml'))
        for user_data in scenario:
            progress.action('Пользователь %s' % user_data['email'])
            user = self._get_user(user_data)

            for estate_data in user_data['estates']:
                estate = self._get_estate(user, estate_data)

                if 'preview' in estate_data:
                    db.session.flush()
                    estate.preview = os.path.join(virtual_root, estate_data['preview'])

                multitour = self._get_multitour(estate)

                for i, tour_data in enumerate(estate_data['tours']):
                    tour = self._get_tour(estate, tour_data)
                    del tour.tour
                    del tour.preview
                    del tour.screen
                    db.session.flush()
                    tour.preview = os.path.join(virtual_root, tour_data['preview'])
                    tour.screen = os.path.join(virtual_root, tour_data['preview'])
                    tour.tour = os.path.join(virtual_root, 'landing/models', tour_data['tour'])

                    if multitour:
                        multitour.tours.append(OfferTour(
                            offer=multitour,
                            tour=tour,
                            sort=i
                        ))

        db.session.commit()

        Recount().run()
        progress.end()
