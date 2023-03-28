import re
import csv
import os
import shutil

from flask import current_app, url_for
from flask_script import Command, Option

from visual.models import Estate, Tour, Offer, OfferTour
from visual.core import db


class MultitoursCreating(Command):
    """Создаёт мультитуры для Румняцево. После окончания проекта — заархивировать."""
    option_list = (
        Option('--estate_id', '-e', default=265, help='Creating multitours from this estate'),
    )

    def __init__(self, func=None):
        super().__init__(func)

    def run(self, estate_id):
        multitour_dict = {}
        position = {'D': (0, 'С мебелью'),
                    'F': (1, 'С отделкой')}

        def create_offer(tour_type, title):
            multitour_title = title.replace(tour_type, '')
            if multitour_title not in multitour_dict:
                multitour = Offer(estate_id=estate_id,
                                  type='multitour',
                                  title_ru=multitour_title,
                                  title_en=multitour_title,
                                  title_de=multitour_title,
                                  title_fr=multitour_title,
                                  template='common',
                                  template_data={'keep_position': True})
                db.session.add(multitour)
                db.session.flush()
                multitour_dict[multitour_title] = multitour
            db.session.add(OfferTour(offer_id=multitour_dict[multitour_title].id,
                                     tour_id=id,
                                     sort=position[tour_type][0],
                                     title=position[tour_type][1]))
            multitour_dict[multitour_title].cnt_tours += 1
            if multitour_dict[multitour_title].cnt_tours > 2:
                current_app.logger.error('В оффере {} более двух туров.'.format(multitour_title))

        try:
            estate_id = int(estate_id)
        except ValueError:
            current_app.logger.error('Estate_id has\'t int value')
            return

        offer_query = db.session.query(Offer).filter(Offer.estate_id == estate_id,
                                                     db.or_(Offer.title_ru.like('%(T%_S%_L%)'),
                                                            Offer.title_ru.like('_T%')))
        for offer in offer_query.all():
            multitour_dict[offer.title_ru] = offer
            for offer_tour in offer.tours:
                db.session.delete(offer_tour)
            offer.cnt_tours = 0
        db.session.commit()

        for id, title in db.session.query(Tour.id, Tour.title).filter(Tour.estate_id == estate_id).order_by(Tour.title).all():
            title = title.strip()
            type_group = re.match(r'\d+([D|F]) \(T\d+_S\d+_L\d+\)$', title)
            if type_group:
                create_offer(type_group.group(1), title)
            else:
                type_group = re.match(r'([D|F])_T\d+$', title)
                if type_group:
                    create_offer(type_group.group(1), title)

        for offer in multitour_dict.values():
            if offer.cnt_tours == 0:
                db.session.delete(offer)

        db.session.commit()

        count_offers = db.session.query(db.func.count(Offer.id)).filter_by(estate_id=estate_id).as_scalar()
        Estate.query.filter_by(id=estate_id).update({'cnt_pr_multitour': count_offers},
                                                    synchronize_session=False)

        db.session.commit()


class MultitoursExporting(Command):

    option_list = (
        Option('--file_folder', '-f', help='Export to file folder'),
        Option('--estate_id', '-e', default=265, help='Creating multitours from this estate'),
    )

    def __init__(self, func=None):
        super().__init__(func)

    def run(self, file_folder, estate_id):
        try:
            estate_id = int(estate_id)
        except ValueError:
            current_app.logger.error('Estate_id has\'t int value')
            return

        if file_folder is None:
            current_app.logger.error('Use " ./py.py multitours-exporting -f /tmp/room-park"')
            return

        offer_query = db.session.query(Offer).filter(Offer.estate_id == estate_id,
                                                     db.or_(Offer.title_ru.like('%(T%_S%_L%)'),
                                                            Offer.title_ru.like('_T%')))
        os.makedirs(file_folder, exist_ok=True)
        try:
            with open(os.path.join(file_folder, 'multitours.csv'), 'w') as csv_file:
                writer = csv.writer(csv_file)
                for offer in offer_query.all():
                    estate_info = re.match(r'\d+ \(T(\d+)_S(\d+)_L(\d+)\)$', offer.title_ru.strip())
                    asset_path = offer.screen.abs_path
                    _, asset_extension = os.path.splitext(asset_path)
                    asset_file_name = '{}{}'.format(offer.title_ru.replace(' ', '_'), asset_extension)
                    if estate_info:
                        writer.writerow([url_for('front.offer', offer_id=offer.id, _external=True, _scheme='https'),
                                         offer.title_ru,
                                         asset_file_name,
                                         estate_info.group(1),
                                         estate_info.group(2),
                                         estate_info.group(3)])
                    shutil.copy(asset_path, os.path.join(file_folder, asset_file_name))

        except BaseException:
            current_app.logger.error('permission denied')
