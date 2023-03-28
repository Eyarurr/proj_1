import requests
from requests.exceptions import ReadTimeout, ConnectionError

from manage.progress import Progress
from urllib.parse import parse_qs, urlparse

from visual.models import Tour

progress = Progress()


class CheckClickable:
    """Проверка на битость ссылок в Tour.meta['clickable']"""
    def run(self, user_id, tour_id):
        links = {}
        errors = {}
        error_links = []
        count = 0

        if user_id:
            tours = Tour.query.filter(Tour.user_id == user_id).all()
        elif tour_id:
            tours = Tour.query.filter(Tour.id == tour_id).all()
        else:
            tours = []

        if not len(tours):
            print('Туров не найдено.')

        for tour in tours:
            if 'clickable' in tour.meta:
                for clickable in tour.meta['clickable']:
                    if 'class' in clickable and 'ad' in clickable['class'].split(' '):
                        buttons = clickable.get('action', {}).get('buttons', [])
                        if buttons and isinstance(buttons, list):
                            try:
                                url = buttons[0].get('url', None)
                            except IndexError:
                                url = None

                            if url:
                                url = parse_qs(urlparse(url).query)['url'][0]
                                links[url] = ''
                                count += 1
        progress.action('Проверяем ссылки...', len(links))
        for url, v in links.items():
            try:
                response = requests.head(url)
                if response.status_code != 200:
                    if response.status_code not in errors:
                        errors[response.status_code] = 1
                    else:
                        errors[response.status_code] += 1
                    error_links.append([url, response.status_code])

            except (ReadTimeout, ConnectionError) as e:
                print(repr(e))

            progress.step()
        print('Ссылок всего:%s' % (count,))
        if not len(errors):
            print('Битых ссылок нет')

        for k, v in errors.items():
            print('Ошибка %s - %s' % (k, v))
        for link in error_links:
            print('http статус %s, ссылка %s' % (link[1], link[0]))

        progress.end()
