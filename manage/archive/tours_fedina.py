import re
import os
import csv
import copy
from math import sqrt
from collections import OrderedDict

import pandas
from flask import current_app
from flask_script import Command, Option
from sqlalchemy.orm.attributes import flag_modified

from visual.models import Tour, Estate, Footage, Offer, OfferTour
from visual.core import db
from .progress import Progress
from .multitours_creating import MultitoursCreating


class FedinaCopyHalls(Command):
    """Копирует холлы на недостающие этажи, расставляются номера на дверях и ссылки на квартиры"""

    option_list = (
        Option('--from_estate_id', '-s', help='ID объекта недвижимости, с которого копируем туры'),
        Option('--to_estate_id', '-d', help='ID объекта недвижимости, в который копируем туры'),
        Option('--shows_estate_id', '-p', help='Объект с презентациями'),
    )

    def run(self, from_estate_id, to_estate_id, shows_estate_id):
        def get_offer_id_by_title(estate_id, title):
            offer = Offer.query.filter(Offer.estate_id == estate_id, Offer.title_ru == title).first()
            return offer.id if offer else None

        def get_floor_delta(floor, border, floor_above):
            if floor < border:
                return (floor - 2) * 19
            if floor >= border:
                return (border-2) * 19 + (floor - border) * floor_above

        if from_estate_id:
            from_estate = Estate.query.filter(Estate.id == from_estate_id).first()
            if not from_estate:
                current_app.logger.error('Исходный объект не найден.')
                return
        else:
            current_app.logger.error('Не задан id исходного объекта.')
            return
        if to_estate_id:
            to_estate = Estate.query.filter(Estate.id == to_estate_id).first()
            if not to_estate:
                current_app.logger.error('Целевой объект не найден.')
                return
        else:
            to_estate = Estate(user_id=from_estate.user_id,
                               title='Дом на улице Федина (все квартиры)')
            db.session.add(to_estate)
            db.session.flush()

        borders = {'A': 30, 'B': 26}
        floors_above = {'A': 12, 'B': 13}

        progression = Progress()
        progression.action('Копируем туры', 4)

        for tour in from_estate.tours:
            tour_info = re.match(r'Floor_(A|B)_(\d+)-(\d+)$', tour.title.strip())
            if tour_info:
                progression.step()
                building = tour_info.group(1)
                floor_start = int(tour_info.group(2))
                floor_end = int(tour_info.group(3))+1
                key = "{}_{}-{}".format(building, tour_info.group(2), tour_info.group(3))
                for current_floor in range(floor_start, floor_end):
                    meta = copy.deepcopy(tour.meta)
                    clickables = meta.get('clickable', None)

                    if not clickables:
                        current_app.logger.error('Кликабельные объекты не найдены для {}'.format(key))
                        pass

                    delta = get_floor_delta(current_floor, borders[building], floors_above[building])

                    for clickable in clickables:
                        if clickable.get('label', None):
                            new_label_text = int(clickable['label']['text']) + delta
                            clickable['label']['text'] = '{num:04d}'.format(num=int(new_label_text))
                        if clickable.get('title', None):
                            offer_id = get_offer_id_by_title(shows_estate_id, '{}_L{}_{}'.
                                                             format(building, current_floor,
                                                                    int(clickable['title'])+delta))
                            clickable['title'] = ''
                            clickable['action'] = {'type': 'href',
                                                   'url': 'https://biganto.com/show/{}'.format(offer_id)}

                    newborn = Tour(footage_id=tour.footage.id,
                                   title='Floor_{}_{}'.format(building, current_floor),
                                   estate_id=to_estate_id,
                                   hidden=tour.hidden,
                                   meta=meta)
                    db.session.add(newborn)
                    db.session.flush()
                    newborn.preview = tour.preview.abs_path
                    newborn.screen = tour.screen.abs_path
                    newborn.files = tour.files.abs_path

                db.session.commit()
                to_estate.recount()
                db.session.commit()
        progression.end()


class FedinaCopyFloors(Command):
    """Копирует туры каждого типа на все этажи, при этом ищется тур нужного типа на ближайшем этаже"""

    option_list = (
        Option('--from_estate_id', '-s', help='ID объекта недвижимости, с которого копируем туры'),
        Option('--types_file', '-f', help='Файл с типами квартир'),
        Option('--to_estate_id', '-d', help='ID объекта недвижимости, в который копируем туры'),
    )

    def run(self, from_estate_id, types_file, to_estate_id):
        if from_estate_id:
            from_estate = Estate.query.options(db.joinedload(Estate.tours)).get(from_estate_id)
            if not from_estate:
                current_app.logger.error('Исходный объект не найден.')
                return
        if to_estate_id:
            to_estate = Estate.query.options(db.joinedload(Estate.tours)).get(to_estate_id)
            if not to_estate:
                current_app.logger.error('Целевой объект не найден.')
                return
        else:
            to_estate = Estate(user_id=from_estate.user_id,
                                title='Дом на улице Федина (все квартиры)')
            db.session.add(to_estate)
            db.session.flush()

        # Раскладываем имеющиеся туры по корпусам/типам/номерам/этажам
        source_tours = {}
        for tour in from_estate.tours:
            tour_info = re.match(r'(A|B)_L(\d+)_(\d+)(D|F)$', tour.title.strip())
            if tour_info:
                try:
                    corpus = tour_info.group(1)
                    floor = int(tour_info.group(2))
                    number = int(tour_info.group(3))
                    facing = tour_info.group(4)
                except ValueError:
                    continue
                if corpus not in source_tours:
                    source_tours[corpus] = {}
                if facing not in source_tours[corpus]:
                    source_tours[corpus][facing] = {}
                if number not in source_tours[corpus][facing]:
                    source_tours[corpus][facing][number] = {}
                source_tours[corpus][facing][number][floor] = tour

        # Читаем максимальный этаж для каждого типа квартиры
        max_floor_types = {}
        count_steps = 0
        try:
            with open(types_file) as import_file:
                reader = list(csv.reader(import_file))
                for row in reader:
                    try:
                        corpus = row[0]
                        number = int(row[1])
                        max_floor = int(row[2])
                        count_steps += 1
                    except (IndexError, ValueError):
                        continue

                    if corpus not in max_floor_types:
                        max_floor_types[corpus] = {}
                    max_floor_types[corpus][number] = max_floor

        except (FileNotFoundError, TypeError):
            current_app.logger.error('Файл "{}" не найден'.format(types_file))
            return

        count = 0
        progression = Progress()
        progression.action('Копируем туры', count_steps)
        for corpus in max_floor_types:
            if corpus not in source_tours:
                progression.say('Для корпуса {} нет ни одного тура.'.format(corpus))
                continue
            for number in max_floor_types[corpus]:
                max_floor = max_floor_types[corpus][number]
                for facing in ('D', 'F'):
                    try:
                        floor_list = source_tours[corpus][facing][number].keys()
                    except KeyError:
                        progression.say('Для квартиры {}{} в корпусе {} нет ни одного тура.'.
                                        format(number, facing, corpus))
                        floor_list = None
                    if floor_list:
                        for floor in range(2, max_floor + 1):
                            nearest_floor = min(floor_list, key=lambda x: abs(x - floor))
                            base_tour = source_tours[corpus][facing][number][nearest_floor]

                            if to_estate_id != from_estate_id or \
                               (to_estate_id == from_estate_id and floor != nearest_floor):
                                title = '{}_L{}_{}{}'.format(corpus, floor, number, facing)
                                newborn = Tour(
                                    footage_id=base_tour.footage.id,
                                    title=title,
                                    estate_id=to_estate.id,
                                    hidden=base_tour.hidden,
                                    meta=base_tour.meta
                                )
                                count += 1

                                db.session.add(newborn)
                                db.session.flush()
                                newborn.preview = base_tour.preview.abs_path
                                newborn.screen = base_tour.screen.abs_path
                                newborn.files = base_tour.files.abs_path
                progression.step()
        progression.say('Скопировано {} туров в объект {}.'.format(count, to_estate.id))
        progression.end()

        db.session.commit()
        to_estate.cnt_tours = len(to_estate.tours)
        db.session.commit()


class FedinaNumber(Command):
    """Переименовывает туры в соответствии с уникальным номером квартиры, который вычисляется на основании
       номера базовой квартиры на этаже (первой для нумерации) и порядке нумерации.
    """

    option_list = (
        Option('--estate_id', '-e', help='ID объекта недвижимости'),
        Option('--start', '-s', default=1, type=int, help='Порядковый номер квартиры на этаже, с которого начинается нумерация'),
        Option('--reverse', '-r', default=False, type=bool, help='Обратный порядок нумерации'),
    )

    def run(self, estate_id, start, reverse):
        if estate_id:
            source_estate = Estate.query.options(db.joinedload(Estate.tours)).get(estate_id)
            if not source_estate:
                current_app.logger.error('Исходный объект не найден.')
                return

        # Раскладываем имеющиеся туры по корпусам/этажам/номерам/типам
        source_tours = {}
        for tour in source_estate.tours:
            tour_info = re.match(r'(A|B)_L(\d+)_(\d+)(D|F)$', tour.title.strip())
            if tour_info:
                corpus = tour_info.group(1)
                floor = int(tour_info.group(2))
                number = int(tour_info.group(3))
                facing = tour_info.group(4)
                if corpus not in source_tours:
                    source_tours[corpus] = {}
                if floor not in source_tours[corpus]:
                    source_tours[corpus][floor] = {}
                if number not in source_tours[corpus][floor]:
                    source_tours[corpus][floor][number] = {}
                source_tours[corpus][floor][number][facing] = tour

        progression = Progress()
        progression.action('Переименование туров', len(source_estate.tours))
        for corpus in source_tours:
            # Нумерация по корпусам
            count = 0
            # Сортируем этажи
            source_tours[corpus] = sorted(source_tours[corpus].items(), key=lambda floor: floor[0])

            for floor in source_tours[corpus]:
                flats = floor[1]
                floor_index = floor[0]
                numbers_list = [int(number) for number in flats.keys()]
                numbers_list = sorted(numbers_list, reverse=reverse)

                # Найдём квартиру, с которой начинается нумерация или следующую ближайшую по номеру,
                # ведь теоретически нужной квартиры может не быть на этаже.
                if reverse:
                    start_list = [i for i in numbers_list if i <= start]
                    # Порядковый номер квартиры, с которой начинается нумерация для текущего этажа.
                    if len(start_list) > 0:
                        start_floor = start_list[0]
                    else:
                        start_floor = max(numbers_list)
                    start_index = numbers_list.index(start_floor)
                    numbers_list = numbers_list[start_index:] + numbers_list[:start_index]
                else:
                    start_list = [i for i in numbers_list if i >= start]
                    if len(start_list) > 0:
                        start_floor = start_list[0]
                    else:
                        start_floor = min(numbers_list)
                    start_index = numbers_list.index(start_floor)
                    numbers_list = numbers_list[start_index:] + numbers_list[:start_index]

                # Теперь в numbers_list правильный порядок номеров квартир в рамках этажа.
                for number in numbers_list:
                    count += 1
                    info = flats[number]
                    for facing in ('D', 'F'):
                        tour = info.get(facing, None)
                        title = '{}_L{}_{}{}'.format(corpus, floor_index, count, facing)
                        if tour:
                            tour.title = title
                            db.session.add(tour)
                            db.session.flush()
                            progression.step()
                        else:
                            progression.say('Нет тура для квартиры {}.'.format(title))
        progression.end()

        db.session.commit()


class FedinaCreateMultitours(Command):
    """Создание мультитуров. Идемпотентный."""

    option_list = (
        Option('--estate_id', '-e', help='ID объекта недвижимости'),
    )

    def run(self, estate_id):
        multitour_dict = {}
        position = {'F': (0, 'С отделкой'),
                    'D': (1, 'С мебелью')}

        try:
            estate_id = int(estate_id)
        except ValueError:
            current_app.logger.error('Идентификатор объекта должен быть целым числом.')
            return

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

        offer_query = db.session.query(Offer).filter(Offer.estate_id == estate_id,
                                                     db.or_(Offer.title_ru.like('A_L%_%'),
                                                            Offer.title_ru.like('B_L%_%')))
        for offer in offer_query.all():
            multitour_dict[offer.title_ru] = offer
            for offer_tour in offer.tours:
                db.session.delete(offer_tour)
            offer.cnt_tours = 0
        db.session.commit()

        for id, title in db.session.query(Tour.id, Tour.title).filter(Tour.estate_id == estate_id).order_by(Tour.title).all():
            title = title.strip()
            type_group = re.match(r'[A|B]_L\d+_\d+(D|F)$', title.strip())
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
