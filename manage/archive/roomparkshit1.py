import re
import os
import csv
from math import sqrt

import pandas
from flask import current_app
from flask_script import Command, Option
from sqlalchemy.orm.attributes import flag_modified

from visual.models import Tour, Folder, Footage
from visual.core import db
from .progress import Progress
from .multitours_creating import MultitoursCreating


class ToursClickableUpdate(Command):
    """Какая-то хуйня для Румянцево. Если понадобится -- перетащить в ephemera. ЗАДОКУМЕНТИРОВАТЬ!!!"""
    option_list = (
        Option('--folder_id', '-e', help='ID Объекта недвижимости у которого надо обновить информацию'),
    )

    def run(self, folder_id):
        clickable_dict = {}
        for tour in Tour.query.filter(Tour.title.like('%D (T%'), Tour.folder_id == folder_id).all():
            if 'clickable' in tour.meta:
                clickable_dict[tour.title.replace('D', 'F')] = tour.meta['clickable']

        for tour in Tour.query.filter(Tour.title.like('%F (T%'), Tour.folder_id == folder_id).all():
            if tour.title in clickable_dict:
                tour.meta['clickable'] = clickable_dict[tour.title]
                flag_modified(tour, 'meta')
        db.session.commit()


class ToursAutoUpdate(Command):
    """Какая-то хуйня для Румянцево. Если понадобится -- перетащить в ephemera. ЗАДОКУМЕНТИРОВАТЬ!!!"""
    option_list = (
        Option('--example_tours_file', '-e', help='CSV file with example tours meta data'),
        Option('--from_folder_id', '-f', default=265, help='Modify only this folder tours'),
    )

    def run(self, example_tours_file, from_folder_id):

        def get_tour_example_key(title):
            type_group = re.match(r'\d+([D|F]) \(T(\d+)_S\d+_L\d+\)$', title)
            return '{}_T{}'.format(type_group.group(1), type_group.group(2))

        def refresh_meta_skyboxes(tour, meta):
            if 'skyboxes' not in tour.meta:
                return
            for skybox_number in tour.meta['skyboxes'].keys():
                if skybox_number in meta:
                    tour.meta['skyboxes'][skybox_number]['title'] = meta[skybox_number]['title']
            flag_modified(tour, 'meta')

        example_tours_dict = {}

        if example_tours_file:
            data = pandas.read_csv(example_tours_file, names=['title'])
            for tour in Tour.query.filter(Tour.title.in_(data.title.tolist()),
                                          Tour.folder_id == from_folder_id):
                example_tours_dict[tour.title] = tour.meta.get('skyboxes')

            for tour in Tour.query.filter(Tour.title.like('%(T%_S%_L%)'),
                                          Tour.folder_id == from_folder_id).all():
                tour_meta_key = get_tour_example_key(tour.title)
                new_meta = example_tours_dict.get(tour_meta_key)
                if new_meta:
                    refresh_meta_skyboxes(tour, new_meta)

        # Базовые шаблоны
        for tour in Tour.query.filter(Tour.title.like('D_T%'), Tour.folder_id == from_folder_id).all():
            if 'base' in tour.title:
                continue
            example_tours_dict[tour.title[1:]] = tour.meta.get('skyboxes')

        for common_tours in Tour.query.filter(Tour.title.like('%_T%'), Tour.folder_id == from_folder_id).all():
            try:
                new_meta = example_tours_dict.get('_' + common_tours.title.split('_')[1])
                if new_meta:
                    refresh_meta_skyboxes(common_tours, new_meta)
            except IndexError:
                continue
        db.session.commit()


class ToursCopier(Command):
    """Какая-то хуйня для Румянцево. Если понадобится -- перетащить в ephemera, переехать на папки, отосюда удалить."""
    option_list = (
        Option('--from_estate_id', '-f', default=265, help='ID Объекта недвижимости с которого копируем туры'),
        Option('--estates_files', '-e', help='Файл с обьектами недвижимости'),
        Option('--to_estate_id', '-t', help='ID Объекта недвижимости в который копируем туры'),
    )

    def run(self, from_estate_id, estates_files, to_estate_id):
        estate = Estate.query.options(db.joinedload(Estate.tours)).get(from_estate_id)
        if not estate:
            current_app.logger.error('Объект недвижимости с которого копируем туры не найден.')
            return
        if to_estate_id:
            new_estate = Estate.query.options(db.joinedload(Estate.tours)).get(to_estate_id)
            if not new_estate:
                current_app.logger.error('Объект недвижимости в который копируем туры не найден.')
                return
        else:
            new_estate = Estate(user_id=estate.user_id,
                                title='Румянцево-Парк (для сайта)')
            db.session.add(new_estate)
            db.session.flush()

        tours_already_in_estate = [tour.title.strip().split(' ')[0] for tour in new_estate.tours]

        base_tours = {'F': {}, 'D': {}}
        bt_footage_ids = []
        current_tours = {'F': {}, 'D': {}}
        for tour in estate.tours:
            tour_info = re.match(r'(D|F)_T(\d+)$', tour.title)
            if tour_info:
                base_tours[tour_info.group(1)][int(tour_info.group(2))] = tour
                bt_footage_ids.append(tour.footage_id)

        for tour in estate.tours:
            tour_info = re.match(r'\d+(D|F) \(T(\d+)_S(\d+)_L(\d+)\)$', tour.title)
            if tour_info and tour.footage_id not in bt_footage_ids:
                facing = tour_info.group(1)
                tour_type = int(tour_info.group(2))
                section = int(tour_info.group(3))
                floor = int(tour_info.group(4))

                if section not in current_tours[facing]:
                    current_tours[facing][section] = {}
                if tour_type not in current_tours[facing][section]:
                    current_tours[facing][section][tour_type] = {}
                if floor not in current_tours[facing][section][tour_type]:
                    current_tours[facing][section][tour_type][floor] = tour

        try:
            with open(estates_files) as import_file:
                reader = list(csv.reader(import_file))
                progression = Progress()
                progression.action('Копируем туры', len(reader)*2)
                for row in reader:
                    try:
                        section = int(row[0])
                        floor = int(row[1])
                        estates_number = int(row[3])
                        tour_type = int(row[7])
                    except ValueError:
                        continue

                    for facing in ('D', 'F'):
                        try:
                            floor_list = current_tours[facing][section][tour_type].keys()
                        except KeyError:
                            floor_list = None
                        if floor_list:
                            nearest_floor = min(floor_list, key=lambda x: abs(x - floor))
                            old_tour = current_tours[facing][section][tour_type][nearest_floor]
                        elif tour_type in base_tours[facing]:
                            old_tour = base_tours[facing][tour_type]
                        else:
                            old_tour = None
                            progression.say('Квартире {}/{}/{}/{} не сопоставлен тур.'.
                                            format(estates_number, tour_type, section, floor))

                        if old_tour:
                            title = '{}{} (T{}_S{}_L{})'.format(estates_number, facing, tour_type, section, floor)
                            tour_identifer = '{}{}'.format(estates_number, facing)
                            bt_tour = Tour.query.filter(Tour.estate_id == new_estate.id,
                                                        Tour.title == title).first()

                            if bt_tour:
                                if bt_tour.footage_id in bt_footage_ids and old_tour.footage_id != bt_tour.footage_id \
                                        and old_tour.footage_id not in bt_footage_ids \
                                        and tour_identifer in tours_already_in_estate:
                                    bt_tour.delete()
                                    tours_already_in_estate.remove(tour_identifer)
                                    progression.say('У квартиры {}/{}/{}/{} базовый тур будет заменен на нормальный.'.
                                                    format(estates_number, tour_type, section, floor))
                            else:
                                if old_tour.footage_id in bt_footage_ids and tour_identifer not in tours_already_in_estate:
                                    progression.say('Квартире {}/{}/{}/{} присвоен базовый тур {}_T{}'.
                                            format(estates_number, tour_type, section, floor, facing, tour_type))

                            if tour_identifer not in tours_already_in_estate:
                                newborn = Tour(
                                    footage_id=old_tour.footage.id,
                                    title=title,
                                    estate_id=new_estate.id,
                                    hidden=old_tour.hidden,
                                    meta=old_tour.meta
                                )

                                db.session.add(newborn)
                                db.session.flush()
                                newborn.preview = old_tour.preview.abs_path
                                newborn.screen = old_tour.screen.abs_path
                                newborn.files = old_tour.files.abs_path
                        progression.step()
                progression.end()

        except (FileNotFoundError, TypeError):
            current_app.logger.error('Файл "{}" не найден'.format(estates_files))

        db.session.commit()
        new_estate.cnt_tours = len(new_estate.tours)
        db.session.commit()
        multitour_creator = MultitoursCreating()
        multitour_creator.run(new_estate.id)
