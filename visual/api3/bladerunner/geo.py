import math
import datetime
import typing
import requests

from flask import current_app

from visual.core import redis


class GeoRouterError(Exception):
    """Общая ошибка геомаршрутизатора"""
    pass


class GeoRouterExternalError(GeoRouterError):
    """Ошибка при работе с внешним API"""
    pass


class GeoRouter:
    CACHE_TIME = 60 * 60 * 24 * 30

    def __init__(self, p1: typing.List[float], p2: typing.List[float], when: datetime.datetime):
        self.p1 = p1
        self.p2 = p2
        self.when = when

    def tta(self) -> int:
        """Возвращает время в минутах, чтобы добраться из точки p1 в точку p2, если выехать в when.
        Возвращает -1, если маршрута не существует.
        Кеширует результат. Использует реальный геомаршрутизатор, если в конфиге приложения есть свойство
        YANDEX_ROUTER_API_KEY. Если его нет, считает приблизительное значение в self.tta_fake().
        """
        dur = redis.get(self._cache_key)
        if dur is not None:
            return int(dur)

        if not current_app.config['YANDEX_ROUTER_API_KEY']:
            current_app.logger.warning('GeoRouter: No YANDEX_ROUTER_API_KEY in config. Using fake router.')
            dur = self.tta_fake()
        else:
            dur = self.tta_real()

        # покури перед съёмкой, братишка
        dur += 3

        redis.setex(self._cache_key, self.CACHE_TIME, dur)
        
        return dur

    @property
    def _cache_key(self):
        key = 'grtr.' + '-'.join([str(round(x, 5)) for x in self.p1 + self.p2]) + '-' + self.when.strftime('%Y%m%d%H%M')
        return key

    def tta_fake(self) -> int:
        """Возвращает время в минутах, чтобы добраться из точки p1 в точку p2, если выехать в when.
        Работает без API маршрутизатора, просто считает длину отрезка, исходя из того, что
        1 градус широты = 111 км (он везде одинаковый)
        1 градус долготы = 64 км (это на широте Москвы)
        Курьер двигается со скоростью 10 км/ч (типа учёт поворотов, светофоров, пробок)
        """
        span_lat = abs(self.p1[0] - self.p2[0]) * 111
        span_lon = abs(self.p1[1] - self.p2[1]) * 64
        distance = math.sqrt(span_lat ** 2 + span_lon ** 2)
        return round(distance / 10 * 60)

    def tta_real(self) -> int:
        """Возвращает время в минутах, чтобы добраться из точки p1 в точку p2, если выехать в when.
        Работает на реальном API геомаршрутизатора.
        Если с API пообщаться не удалось, выбрасывает `GeoRouterError`
        """
        url = 'https://api.routing.yandex.net/v2/route'
        qs = {
            'apikey': current_app.config['YANDEX_ROUTER_API_KEY'],
            'mode': 'driving',
            'departure_time': int(self.when.timestamp()),
            'waypoints': f'{self.p1[0]},{self.p1[1]}|{self.p2[0]},{self.p2[1]}'
        }

        try:
            res = requests.get(url, params=qs)
        except requests.exceptions.RequestException as e:
            raise GeoRouterExternalError(e)

        if res.status_code != 200:
            raise GeoRouterExternalError(f'External API status: {res.status_code}, {res.text}')

        resp_data = res.json()
        leg = resp_data['route']['legs'][0]
        if leg['status'] != 'OK':
            return -1

        dur = 0
        for step in resp_data['route']['legs'][0]['steps']:
            dur += step['duration']

        dur = int(math.ceil(dur / 60))

        return dur
