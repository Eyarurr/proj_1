from visual.models import Tour
from visual.core import db

from sqlalchemy.orm.attributes import flag_modified

from_estate_id = 280
to_estate_id = 321

tours = db.session.query(Tour).filter(Tour.estate_id == from_estate_id).all()

for tour in tours:
    new_footage = tour.footage

    newborn = Tour(
        footage_id=new_footage.id,
        title=tour.title,
        estate_id=to_estate_id,
        hidden=tour.hidden,
        created_by=121,
        meta={}
    )

    db.session.add(newborn)
    db.session.flush()
    newborn.preview = tour.preview.abs_path
    newborn.screen = tour.screen.abs_path
    newborn.meta = tour.meta
    newborn.files = tour.files.abs_path
db.session.commit()

for tour in tours:
    if 'clickable' in tour.meta:
        del tour.meta['clickable']
        flag_modified(tour, 'meta')
db.session.commit()
