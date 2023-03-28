import json
import requests
from types import SimpleNamespace

from flask import current_app
from requests import ReadTimeout, ConnectionError

from visual.models import User, Folder, Offer, OfferTour
from visual.core import db
from . import AcquireTours


class AcquireMultitours:
    """Переносит мультитуры из разных юрисдикций"""
    HOST_PORT = 22
    LOCAL_ASSET_STORAGE_ROOT = None
    JURISDICTIONS_HOSTS = None
    LOCAL_JURISDICTION = None

    def run(self, jurisdiction, remote_multitour_id=None, remote_folder_id=None, remote_user_id=None):
        AcquireTours.HOST_PORT = self.__class__.HOST_PORT = 22
        AcquireTours.LOCAL_ASSET_STORAGE_ROOT = self.__class__.LOCAL_ASSET_STORAGE_ROOT = current_app.config.get('ASSET_STORAGE_ROOT')
        AcquireTours.JURISDICTIONS_HOSTS = self.__class__.JURISDICTIONS_HOSTS = current_app.config.get('JURISDICTIONS_HOSTS')
        AcquireTours.LOCAL_JURISDICTION = self.__class__.LOCAL_JURISDICTION = current_app.config.get('JURISDICTION')

        if jurisdiction == self.LOCAL_JURISDICTION:
            print('Юрисдикция совпадает с локальной!')
            quit()

        user_data = AcquireTours.user_auth(jurisdiction)
        AcquireTours.check_user_access(jurisdiction, SimpleNamespace(**user_data))

        if remote_folder_id and remote_user_id:
            self.transfer_folder(jurisdiction, remote_user_id, remote_folder_id, user_data)
        elif remote_multitour_id:
            offer = self.get_remote_multitour_params(jurisdiction, remote_multitour_id, user_data['auth_token'])
            self.transfer_offer(offer, jurisdiction, user_data)

    @classmethod
    def get_remote_multitour_params(cls, jurisdiction, remote_multitour_id, auth_token):
        try:
            response = requests.get('https://{}/api/v3/offers/{}?client=site.admin&client_version=1.0&auth_token={}&'
                                    .format(cls.JURISDICTIONS_HOSTS[jurisdiction]['host'], remote_multitour_id, auth_token),
                                    verify=False)

            if response.status_code == 200:
                offer = response.json()['result']
                return offer
            else:
                print('Ошибка при получении данных мультитура, код ответа {}'.format(response.status_code))
                print(response.text)
                quit()
        except (ReadTimeout, ConnectionError) as e:
            print(repr(e))

    @classmethod
    def transfer_offer(cls, offer, jurisdiction, user_data):
        multitour_user_data = AcquireTours.get_tour_user_info(jurisdiction, user_data['auth_token'], offer['user_id'])
        multitour_folder_title = AcquireTours.get_tour_folder_title(jurisdiction, user_data['auth_token'],
                                                                    offer['user_id'], offer.get('folder_id', None))
        new_multitour_data = cls.create_user_and_folder(multitour_user_data, multitour_folder_title, offer)

        if 'tours' in offer and len(offer.get('tours', [])) > 0:
            tours = offer['tours']
            for tour in tours:
                new_tour_id = AcquireTours().run(jurisdiction, remote_tour_id=tour['tour_id'],
                                                 multi=True, user_data=user_data)
                tour['tour_id'] = new_tour_id

            remote_multitour_id = offer['id']
            for rm_val in ('id','tours','created_by'):
                offer.pop(rm_val, None)

            offer['user_id'] = new_multitour_data['new_multitour_user_id']
            offer['folder_id'] = new_multitour_data['new_multitour_folder_id']
            new_offer = Offer(**offer)
            db.session.add(new_offer)
            db.session.flush()

            for tour in tours:
                offer_tour = OfferTour(
                    offer_id=new_offer.id,
                    tour_id=tour['tour_id'],
                    sort=tour['sort'],
                    title=tour['title']
                )
                db.session.add(offer_tour)
            db.session.commit()

            cls.persist_jurisdiction_changes(jurisdiction, user_data['auth_token'], remote_multitour_id, new_offer.id)
            cls.delete_multitour(jurisdiction, remote_multitour_id, user_data['auth_token'])
            print('Мультитур с remote_id {} перенесен.'.format(remote_multitour_id))
        else:
            print('В мультитуре {} нет туров. Мультитур не будет скопирован.'.format(offer.title_en))

    def transfer_folder(cls, jurisdiction, remote_user_id, remote_folder_id, user_data):
        try:
            response = requests.get('https://{}/api/offers.getBadges?client=site.admin&client_version=1.0&'
                                    'user_id={}&estate_id={}&auth_token={}&v=2.0&types=multitour'
                                    .format(cls.JURISDICTIONS_HOSTS[jurisdiction]['host'],
                                            remote_user_id, remote_folder_id, user_data['auth_token']), verify=False)
            if response.status_code != 200:
                print('Ошибка при получении мультитуров из папки, код ответа {}'.format(response.status_code))
                print(response.text)
                quit()
            else:
                response_json_result = response.json()
                for multitour in response_json_result:
                    remote_multitour_id = multitour['id']
                    offer = cls.get_remote_multitour_params(jurisdiction, remote_multitour_id, user_data['auth_token'])
                    cls.transfer_offer(offer, jurisdiction, user_data)
        except (ReadTimeout, ConnectionError) as e:
            print(repr(e))
        quit()

    @classmethod
    def create_user_and_folder(cls, multitour_user_data, multitour_folder_title, offer):
        # Проверяем пользователя - нет создаем
        user = User.query.filter(db.func.lower(User.email) == multitour_user_data['tour_user_email']).first()
        if not user:
            folder = None
            new_user = User(
                email=multitour_user_data['tour_user_email'],
                name=multitour_user_data['tour_user_name'],
                password_hash=User.hash_password('tmpPass%1.'),
                email_notifications=0,
                email_confirmed=False
            )
            db.session.add(new_user)
            db.session.commit()
            folder_user_id = new_user.id
            print('Юзер с именем: {} и email: {} создан'.format(new_user.name, new_user.email))
        else:
            # Проверяем папку мультитура
            folder = Folder.query.filter(Folder.title == multitour_folder_title, Folder.user_id == user.id).first()
            folder_user_id = user.id

        if not folder and offer.get('folder_id', False):
            folder = Folder(user_id=folder_user_id, title=multitour_folder_title)
            db.session.add(folder)
            db.session.commit()
        folder_id = folder.id if offer.get('folder_id', False) else None

        return {'new_multitour_user_id': folder_user_id, 'new_multitour_folder_id': folder_id}

    @classmethod
    def persist_jurisdiction_changes(cls, jurisdiction, auth_token, remote_multitour_id, new_multitour_id):
        try:
            response = requests.post('https://{}/api/v3/offers/changed_jurisdiction?client=site.admin&client_version=1.0'
                                     '&auth_token={}'.format(cls.JURISDICTIONS_HOSTS[jurisdiction]['host'], auth_token),
                                     data=json.dumps({'local_id': remote_multitour_id, 'remote_id': new_multitour_id,
                                                      'moved_to': cls.LOCAL_JURISDICTION}),
                                     headers={'Content-type': 'application/json'}, verify=False)

            if response.status_code != 200:
                print('Ошибка при изменении юрисдикций мультитура на удаленной машине, код ответа {}'
                      .format(response.status_code))
                print(response.text)
        except (ReadTimeout, ConnectionError) as e:
                print(repr(e))

    @classmethod
    def delete_multitour(cls, jurisdiction, remote_multitour_id, auth_token):
        try:
            response = requests.delete('https://{}/api/v3/offers/{}?client=site.admin&client_version=1.0&auth_token={}'
                                       .format(cls.JURISDICTIONS_HOSTS[jurisdiction]['host'], remote_multitour_id, auth_token),
                                        verify=False)

            if response.status_code != 204:
                print('Ошибка при удалении мультитура на удаленной машине, код ответа {}'
                      .format(response.status_code))
                print(response.text)
        except (ReadTimeout, ConnectionError) as e:
                print(repr(e))
