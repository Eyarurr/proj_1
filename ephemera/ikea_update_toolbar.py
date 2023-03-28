from visual.models import Tour
from visual.core import db
from sqlalchemy.orm.attributes import flag_modified

target_estate_id = 298
ad_button = {
    "action": {
        "class": "ad",
        "type": "clickable_toggle_class"
    },
    "class": "ad",
    "init": "on",
    "off": {
        "icon": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 223.58225 264.41682'><path d='M113.45779,8.79182h-3.75l-61.75,62-.125,193.625h128v-193Zm-2,84.25a18.75,18.75,0,1,1,18.75-18.75A18.75,18.75,0,0,1,111.45779,93.04182Z' style='fill:#201600;opacity:0.5'/><path d='M124.45779,3.54182h-3.75l-61.75,62-.125,193.625h128v-193Zm-2,84.25a18.75,18.75,0,1,1,18.75-18.75A18.75,18.75,0,0,1,122.45779,87.79182Z' style='fill:#c82b31'/></svg>",
        "title": "Включить информацию о мебели"
    },
    "on": {
        "icon": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 223.58225 264.41682'><path d='M113.45779,8.79182h-3.75l-61.75,62-.125,193.625h128v-193Zm-2,84.25a18.75,18.75,0,1,1,18.75-18.75A18.75,18.75,0,0,1,111.45779,93.04182Z' style='fill:#201600;opacity:0.5'/><path d='M124.45779,3.54182h-3.75l-61.75,62-.125,193.625h128v-193Zm-2,84.25a18.75,18.75,0,1,1,18.75-18.75A18.75,18.75,0,0,1,122.45779,87.79182Z' style='fill:#c82b31'/><line x1='4.20779' y1='259.16682' x2='219.37446' y2='3.54182' style='fill:none;stroke:#000;stroke-miterlimit:10;stroke-width:11px;opacity:0.5'/></svg>",
        "title": "Отключить информацию о мебели"
    }
}

tours = db.session.query(Tour).filter(Tour.estate_id == target_estate_id).all()

for tour in tours:
    if 'toolbar' in tour.meta:
        if len(tour.meta['toolbar']) > 0:
            for button in tour.meta['toolbar'].copy():
                if 'action' in button and 'class' in button['action']:
                    if button['action']['class'] == 'ad':
                        tour.meta['toolbar'].remove(button)
                        tour.meta['toolbar'].append(ad_button)
        else:
            tour.meta['toolbar'].append(ad_button)
    else:
        tour.meta['toolbar'] = [ad_button]

    flag_modified(tour, 'meta')

db.session.commit()
