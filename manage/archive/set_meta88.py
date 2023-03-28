from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import or_

from visual.models import Tour
from visual.core import db


class SetMeta88:
    """Массовая установка тулбаров в турах Румянцево."""
    def run(self, folders):
        folders = list(map(int, folders.split(','))) if folders is not None else []

        tour_query = Tour.query.filter(Tour.folder_id.in_(folders),
                                       or_(Tour.title.like('%(T%_S%_L%)'),
                                           Tour.title.like('%D_T%'),
                                           Tour.title.like('%F_T%')))

        for tour in tour_query.all():
            tour.meta["toolbar"] = [{"action": {"target": "_parent", "type": "tour", "id": "9289"},
                                     "icon": "<svg version='1.1' xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' x='0px' y='0px' viewBox='0 0 76.2 80.8' style='enable-background:new 0 0 76.2 80.8;' xml:space='preserve'><g><polygon points='59.5,23.7 53.9,29.4 60.9,36.4 28.2,36.4 28.2,44.4 60.9,44.4 53.9,51.4 59.5,57.1 76.2,40.4'/><polygon points='45.3,72.8 8,72.8 8,8 45.3,8 45.3,16.6 53.3,16.6 53.3,0 0,0 0,80.8 53.3,80.8 53.3,64.2 45.3,64.2'/></g></svg>",
                                     "title": "Выход во двор"}]
            flag_modified(tour, 'meta')
        db.session.commit()
