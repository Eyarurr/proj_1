import re

from urllib.parse import quote_plus
from visual.models import Tour, Estate
from visual.core import db
from sqlalchemy.orm.attributes import flag_modified
from manage.progress import Progress


progress = Progress()
type2plan = {
    '4к-2':	1,
    '1с-1':	2,
    '2к-1р': 3,
    '3к-2':	4,
    '2к-4л': 5,
    '1к-3 (3)':	6,
    '3к-3':	7,
    '1к-1':	8,
    '2к-1р (2)': 9,
    '1с-3': 10,
    '1с-3 (1)':	11,
    '1к-3 (1)':	12,
    '2к-1р (3)': 13,
    '2к-1р (4)': 14,
    '2к-6л': 15,
    '3к-6 (7)':	16,
    '1к-2':	17,
    '1к-11': 18,
    '2к-5л': 19,
    '2к-4р': 20,
    '1к-9':	21,
    '2к-2л': 22,
    '3к-6 (1)':	23,
    '3к-6 (2)':	24,
    '3к-6 (3)':	25,
    '3к-6 (6)':	26,
    '2к-6л (2)': 27,
    '3к-6 (4)':	28,
    '3к-2 (1)':	29,
    '2к-2р (5)': 30,
    '2к-2р (1)': 31,
    '1с-2':	32,
    '1с-3 (2)':	33,
    '1к-5':	34,
    '2к-2р (4)': 35,
    '1с-4':	36,
    '1к-4':	37,
    '1к-6':	38,
    '3к-1':	39,
    '2к-1л': 40,
    '2к-1л (1)': 41,
    '2к-3л': 42,
    '1к-6 (1)':	43,
    '1к-2 (1)':	44,
    '3к-5':	45,
    '1с-4 (3)':	46,
    '1с-1 (2)':	47,
    '2к-7л': 48,
    '3к-5 (1)':	49,
    '1к-10 (1)': 50,
    '2к-7л (1)': 51,
    '3к-4':	52,
    '1к-8':	53,
    '1к-7':	54,
    '1к-8 (1)':	55,
    '1к-7 (1)':	56,
    '3к-6 (5)':	57,
    '2к-8л': 58,
    '4к-4':	59,
    '1к-3 (2)':	60,
    '1с-1 (1)':	61,
    '2к-1р (1)': 62,
    '4к-4 (1)':	63,
    '1к-11 (1)': 64,
    '1с-3 (3)':	65,
    '2к-7л (2)': 66,
    '2к-2р (3)': 67,
    '2к-2л (2)': 68,
    '2к-6л (1)': 69,
    '2к-2р (2)': 70,
    '2к-2р': 71,
    '2к-1л (2)': 72,
    '1к-3':	73,
    '1к-5 (2)':	74,
    '1с-3 (4)':	75,
    '1к-6 (3)':	76,
    '1к-4 (3)': 77,
    '2к-2л (1)': 78,
    '2к-5л (1)': 79,
    '3к-6':	80,
    '1с-4 (2)':	81,
    '1к-5 (1)':	82,
    '1к-4 (2)':	83,
    '1с-4 (1)':	84,
    '1к-6 (2)':	85,
    '1к-4 (1)':	86,
    '1к-10': 87,
    '4к-3':	88
}

count = 0
type2plan_ = type2plan.copy()
base_estate_id = 321
target_estate_id = 298
ad_button = {
    'action': {
        'class': 'ad',
        'type': 'clickable_toggle_class'
    },
    'class': 'ad',
    'init': 'on',
    'off': {
        'text': 'Включить рекламу'
    },
    'on': {
        'text': 'Выключить рекламу'
    }
}

tours = db.session.query(Tour).filter(Tour.estate_id == base_estate_id).all()
titles = []

for tour in tours:
    titles.append(tour.title)
    if tour.title in type2plan:
        print('Тур # %s найден.' % tour.title)
        del type2plan[tour.title]
        titles.remove(tour.title)

print('---------------------------------------')
if len(titles):
    print('Остались туры:')
    print(titles)
for k, v in type2plan.items():
    print('Тур с # %s не найден' % k)


base_tours = db.session.query(Tour).filter(Tour.estate_id == base_estate_id).all()
progress.action('Множим clickables...', len(base_tours))

for base_tour in base_tours:

    if base_tour.title in type2plan_:
        pattern = '%D (T{}_S%_L%)%' . format(type2plan_[base_tour.title])
        tours = db.session.query(Tour).filter(Tour.estate_id == target_estate_id, Tour.title.like(pattern)).all()

        if 'clickable' in base_tour.meta:
            clickables = base_tour.meta['clickable']
            clickables_ = []
            links = []

            for c in clickables:
                title_ = c.get('title', None)
                title = c.get('action', {}).get('title', None)
                body = c.get('action', {}).get('body', None)

                if title_:
                    title_ = re.sub(r'(?:\d+\s+)?(?:\d+\s+)?\d+\s+руб(\.)?(\r+)?(\n+)?', '', title_,
                                    flags=re.I | re.M)
                    c['title'] = title_
                if title:
                    title = re.sub(r'(?:\d+\s+)?(?:\d+\s+)?\d+\s+руб(\.)?(\r+)?(\n+)?', '', title,
                                   flags=re.I | re.M)
                    c['action']['title'] = title
                if body:
                    body = re.sub(r'(?:\d+\s+)?(?:\d+\s+)?\d+\s+руб(\.)?(\r+)?(\n+)?', '', body, flags=re.I | re.M)
                    c['action']['body'] = body

                c['class'] = 'ad'
                clickables_.append(c.copy())

                buttons = c.get('action', {}).get('buttons', [])
                if buttons and isinstance(buttons, list):
                    links.append(c['action']['buttons'][0]['url'])

            for tour in tours:
                if 'clickable' in tour.meta:
                    for c in tour.meta['clickable'].copy():
                        if 'class' in c and 'ad' in c['class'].split(' '):
                            tour.meta['clickable'].remove(c)
                    tour.meta['clickable'] = tour.meta['clickable'] + clickables_
                else:
                    tour.meta['clickable'] = [] + clickables_

                k = 0
                for i, x in enumerate(tour.meta['clickable'].copy()):
                    if 'class' in x and 'ad' in x['class'].split(' '):
                        buttons = x.get('action', {}).get('buttons', [])

                        if buttons and isinstance(buttons, list):
                            url = quote_plus(links[k])

                            tour.meta['clickable'][i]['action']['buttons'][0]['url'] = \
                                'https://biganto.com/misc/ikea/?url=' + url + '&tour_id=' + str(tour.id)
                            k += 1
                if 'toolbar' in tour.meta:
                    for button in tour.meta['toolbar'].copy():
                        if 'action' in button and 'class' in button['action']:
                            if button['action']['class'] == 'ad':
                                break
                                #tour.meta['toolbar'].remove(button)
                    else:
                        tour.meta['toolbar'].append(ad_button)
                else:
                    tour.meta['toolbar'] = [ad_button]

                count += 1
                flag_modified(tour, 'meta')
                db.session.commit()
    progress.step()
progress.say('Обработано %s туров.' % count)
progress.end()
