from visual.models import Tour, Offer, OfferTour, Estate
from visual.core import db
import re
from sqlalchemy.orm.attributes import flag_modified


tours = db.session.query(Tour).filter(Tour.estate_id == 298).all()
floor_pattern = re.compile('(?i)floor_c(\d+)_l(\d+)')
new_floor_pattern = re.compile('(?i)nw_floor_c(\d+)_l(\d+)')


for tour_original in tours:
    if floor_pattern.findall(tour_original.title) and not new_floor_pattern.findall(tour_original.title):
        section = int(floor_pattern.findall(tour_original.title)[0][0])
        floor = int(floor_pattern.findall(tour_original.title)[0][1])
        corresponding_tour = None
        for tour_new in tours:
            if new_floor_pattern.findall(tour_new.title):
                section_new = int(floor_pattern.findall(tour_new.title)[0][0])
                floor_new = int(floor_pattern.findall(tour_new.title)[0][1])
                if section_new == section:
                    if not corresponding_tour:
                        corresponding_tour = tour_new
                    else:
                        corresponding_tour_floor = int(floor_pattern.findall(corresponding_tour.title)[0][1])
                        if abs(corresponding_tour_floor - floor) == abs(floor_new - floor):
                            corresponding_tour = corresponding_tour if corresponding_tour_floor > floor_new else tour_new
                        elif abs(corresponding_tour_floor - floor) > abs(floor_new - floor):
                            corresponding_tour = tour_new
                        else:
                            corresponding_tour = corresponding_tour

        if corresponding_tour:
            tour_original.footage = corresponding_tour.footage

db.session.commit()