import logging, os
from zipfile import ZipFile
from io import BytesIO

import requests, numpy

from visual.models import Country, City
from visual.core import db


log = logging.getLogger(__name__)
log.setLevel(logging.WARNING)


class UpdateGeoData:
    """Обновляет геоданные из maxmind"""
    ARCHIVE_URL = 'https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City-CSV&license_key=gUplmu5mnq6Xpp2w&suffix=zip'

    def run(self):
        cities_content, ranges_content = self.get_maxmind_content()
        self.save_geo_models(cities_content)
        self.save_nginx_geo_data(ranges_content)

    def save_geo_models(self, cities_content):
        country_data, city_data = cities_content
        self.update_model(Country, self.get_countrys(country_data))
        self.update_model(City, self.get_cities(city_data))

    def save_nginx_geo_data(self, ranges_content):
        import pandas
        ranges_data = pandas.read_csv(BytesIO(ranges_content),
                                      usecols=[0, 1],
                                      na_values=['None'],
                                      keep_default_na=False,
                                      low_memory=False)
        ranges_data = ranges_data[ranges_data.geoname_id != '']

        os.makedirs('var/geo_data', exist_ok=True)

        try:
            os.remove('var/geo_data/city.txt')
        except (OSError, IOError):
            pass

        ranges_data.to_csv('var/geo_data/city.txt',
                           index=False,
                           header=False,
                           sep=' ',
                           line_terminator=';\n')

    def get_archive(self):
        archive = requests.get(self.ARCHIVE_URL, stream=True)
        if archive.status_code != 200:
            log.error("dev.maxmind.com status: {}".format(archive.status_code))
        return ZipFile(BytesIO(archive.content))

    def get_maxmind_content(self):
        try:
            with self.get_archive() as archive:
                return self.multiling_locations(archive), \
                       self.get_csv_file_in_archive(archive, name='Blocks-IPv4.csv')
        except (OSError, IOError) as e:
            log.error("CSV file not found: {}".format(e))

    def get_csv_file_in_archive(self, archive, name):
        for file_name in archive.namelist():
            if name in file_name:
                return archive.open(file_name).read()

    def multiling_locations(self, archive):
        city_data = self.get_csv_file_in_archive(archive, name='Locations-ru.csv')
        country, city = self.get_geo_data(city_data)
        for lang in ['en', 'de', 'fr']:
            city_data = self.get_csv_file_in_archive(archive, name='Locations-{}.csv'.format(lang))
            country_lang, city_lang = self.get_geo_data(city_data)

            country = numpy.concatenate((country, country_lang), axis=1)
            city = numpy.concatenate((city, city_lang), axis=1)
        return (country, city)


    def get_geo_data(self, geo_content):
        import pandas
        city_data = pandas.read_csv(BytesIO(geo_content),
                                    usecols=[0, 4, 5, 10],  na_values=['None'], keep_default_na=False)
        city_data = city_data[city_data.country_iso_code != '']
        country_data = city_data[['country_iso_code', 'country_name']].drop_duplicates(subset=['country_iso_code'])
        city_data = city_data[['geoname_id', 'city_name', 'country_iso_code']]
        return numpy.array(country_data), numpy.array(city_data)

    def update_country_model(self, data):
        countries_id = {country.id: country for country in db.session.query(Country).all()}
        vfunc = numpy.vectorize(lambda id, name: Country(id=id, name=name))
        for country in vfunc(data[:,0], data[:,1]):
            if not countries_id.get(country.id, None):
                db.session.add(country)
            else:
                countries_id.get(country.id).name = country.name
        db.session.commit()

    def update_model(self, model, data):
        exemplar_dict = {exemplar.id: exemplar for exemplar in db.session.query(model).all()}
        for exemplar in data:
            if not exemplar_dict.get(exemplar.id, None):
                db.session.add(exemplar)
            else:
                exemplar_dict.get(exemplar.id).name_ru = exemplar.name_ru
                exemplar_dict.get(exemplar.id).name_en = exemplar.name_en
                exemplar_dict.get(exemplar.id).name_de = exemplar.name_de
                exemplar_dict.get(exemplar.id).name_fr = exemplar.name_fr
        db.session.commit()

    def get_countrys(self, countries):
        def country_model(id, name_ru, name_en, name_de, name_fr):
            return Country(id=id,
                           name_ru=name_ru if name_ru != '' else None,
                           name_en=name_en if name_en != '' else None,
                           name_de=name_de if name_de != '' else None,
                           name_fr=name_fr if name_fr != '' else None)
        get_exemplars = numpy.vectorize(country_model)
        return get_exemplars(countries[:, 0],
                             countries[:, 1],
                             countries[:, 3],
                             countries[:, 5],
                             countries[:, 7])

    def get_cities(self, cities):
        def city_model(id, name_ru, country_id, name_en, name_de, name_fr):
            return City(id=id,
                        name_ru=name_ru if name_ru != '' else None,
                        country_id=country_id,
                        name_en=name_en if name_en != '' else None,
                        name_de=name_de if name_de != '' else None,
                        name_fr=name_fr if name_fr != '' else None)
        get_exemplars = numpy.vectorize(city_model)
        return get_exemplars(cities[:, 0],
                             cities[:, 1],
                             cities[:, 2],
                             cities[:, 4],
                             cities[:, 7],
                             cities[:, 10])
