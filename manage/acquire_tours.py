import os
import sys
import json
import requests
from scp import SCPClient, SCPException
from types import SimpleNamespace
from paramiko import SSHClient, AuthenticationException, SSHException

from flask import current_app
from requests import ReadTimeout, ConnectionError

from visual.models import Folder, Tour, Footage, User
from visual.core import db


class AcquireTours:
    """Переносит туры и съёмки из разных юрисдикций"""
    HOST_PORT = 22
    LOCAL_ASSET_STORAGE_ROOT = None
    JURISDICTIONS_HOSTS = None
    LOCAL_JURISDICTION = None

    def run(self, jurisdiction, remote_tour_id=None, remote_folder_id=None, remote_user_id=None, multi=False,
            user_data=None):
        self.__class__.HOST_PORT = 22
        self.__class__.LOCAL_ASSET_STORAGE_ROOT = current_app.config.get('ASSET_STORAGE_ROOT')
        self.__class__.JURISDICTIONS_HOSTS = current_app.config.get('JURISDICTIONS_HOSTS')
        self.__class__.LOCAL_JURISDICTION = current_app.config.get('JURISDICTION')

        if jurisdiction == self.LOCAL_JURISDICTION:
            print('Юрисдикция совпадает с локальной!')
            quit()

        if not multi:
            user_data = self.user_auth(jurisdiction)
            self.check_user_access(jurisdiction, SimpleNamespace(**user_data))
        else:
            user_data = user_data

        def transfer_tour(jurisdiction, remote_tour_id, user_data, multi):
            print('Копируем тур с ID: {}                                                       '.format(remote_tour_id))
            tour_params = self.get_remote_tour_params(jurisdiction, remote_tour_id, user_data['auth_token'])
            tour_user_data = self.get_tour_user_info(jurisdiction, user_data['auth_token'], tour_params['tour_user_id'])
            tour_folder_title = self.get_tour_folder_title(jurisdiction, user_data['auth_token'],
                                                           tour_params['tour_user_id'], tour_params['tour_folder_id'])
            tour_params_ns = SimpleNamespace(**tour_params)
            tour_params_ns.tour_user_email = tour_user_data['tour_user_email']
            tour_params_ns.tour_user_name = tour_user_data['tour_user_name']
            tour_params_ns.tour_folder_title = tour_folder_title
            new_tour_id = self.create_tour(jurisdiction, tour_params_ns)
            self.persist_jurisdiction_changes(jurisdiction, user_data['auth_token'], remote_tour_id, new_tour_id)
            self.delete_tour(jurisdiction, remote_tour_id, user_data['auth_token'])
            print('Готово!                                                                                     ')
            if multi:
                return new_tour_id

        def transfer_folder(self, jurisdiction, user_data):
            try:
                response = requests.get('https://{}/api/v3/tours?client=site.my&client_version=1.0&'
                                        'user_id={}&folder_id={}&auth_token={}'
                                        .format(self.JURISDICTIONS_HOSTS[jurisdiction]['host'],
                                                remote_user_id, remote_folder_id, user_data['auth_token']), verify=False)
                if response.status_code != 200:
                    print('Ошибка при получении туров из папки, код ответа {}'.format(response.status_code))
                    print(response.text)
                    quit()
                else:
                    response_json_result = response.json()['result']
                    for tour in response_json_result:
                        remote_tour_id = tour['id']
                        transfer_tour(jurisdiction, remote_tour_id, user_data, multi)
            except (ReadTimeout, ConnectionError) as e:
                print(repr(e))
            quit()

        def transfer_user(self, jurisdiction, user_data):
            try:
                response = requests.get('https://{}/api/v3/tours?client=site.my&client_version=1.0&'
                                        'user_id={}&folder_id=-1&auth_token={}'
                                        .format(self.JURISDICTIONS_HOSTS[jurisdiction]['host'],
                                                remote_user_id, user_data['auth_token']), verify=False)
                if response.status_code != 200:
                    print('Ошибка при получении туров юзера, код ответа {}'.format(response.status_code))
                    print(response.text)
                    quit()
                else:
                    response_json_result = response.json()['result']
                    for tour in response_json_result:
                        remote_tour_id = tour['id']
                        transfer_tour(jurisdiction, remote_tour_id, user_data, multi)
            except (ReadTimeout, ConnectionError) as e:
                print(repr(e))
            quit()

        if remote_folder_id and remote_user_id:
            transfer_folder(self, jurisdiction, user_data)
        elif remote_user_id:
            transfer_user(self, jurisdiction, user_data)
        elif remote_tour_id:
            if multi:
                return transfer_tour(jurisdiction, remote_tour_id, user_data, multi)
            else:
                transfer_tour(jurisdiction, remote_tour_id, user_data, multi)

    @classmethod
    def copy_via_ssh(cls, src_path, dst_path, params, r=True):
        host = params['host']
        host_user = params['host_user']

        try:
            ssh_client = SSHClient()
            ssh_client.load_system_host_keys()
            ssh_client.connect(host, cls.HOST_PORT, host_user)
            ssh_client.get_transport().default_window_size = 2147483647
            stdin, stdout, stderr = ssh_client.exec_command(
                'cat /srv/biganto.com/visual/config.local.py | grep ASSET_STORAGE_ROOT | cut -d "=" -f2')
            REMOTE_ASSET_STORAGE_ROOT = stdout.read().decode().strip().strip('\'')

            def progress(filename, size, sent):
                sys.stdout.write(" Копируем: %s  :  %.2f%%                    \r"
                                 % (filename.decode('utf-8') if type(filename) == bytes else filename,
                                    float(sent) / float(size) * 100))

            scp_client = SCPClient(ssh_client.get_transport(), progress=progress)
            if r:
                scp_client.get(os.path.join(REMOTE_ASSET_STORAGE_ROOT, src_path, '.'), dst_path, recursive=True)
            else:
                scp_client.get(os.path.join(REMOTE_ASSET_STORAGE_ROOT, src_path), dst_path)
        except AuthenticationException:
            print("Аунтефикация неудачна. Проверьте логин/пароль.")
        except SSHException as sshException:
            print("Не удалось установить соединение SSH: %s" % sshException)
        except SCPException as scpException:
            print("Не удалось передать файл: %s" % scpException)
        finally:
            scp_client.close()
            ssh_client.close()

    @classmethod
    def user_auth(cls, jurisdiction):
        user_login = input('Логин:')
        user_pass = input('Пароль:')

        try:
            response = requests.post('https://{}/api/v3/users/login?client=site.admin&client_version=1.0'
                                     .format(cls.JURISDICTIONS_HOSTS[jurisdiction]['host']),
                                     data=json.dumps({'email': user_login, 'password': user_pass}),
                                     headers={'Content-type': 'application/json'}, verify=False)
            if response.status_code != 200:
                print('Ошибка при авторизации, код ответа {}'.format(response.status_code))
                print(response.text)
                quit()
            else:
                response_json_result = response.json()['result']
                return {
                    'user_id': response_json_result['user']['id'],
                    'auth_token': response_json_result['token']
                }
        except (ReadTimeout, ConnectionError) as e:
                print(repr(e))

    @classmethod
    def check_user_access(cls, jurisdiction, ns):
        try:
            response = requests.get('https://{}/api/v3/users/{}?client=site.admin&client_version=1.0&auth_token={}&'
                                    'fields=team_member.roles'.format(cls.JURISDICTIONS_HOSTS[jurisdiction]['host'],
                                                                      ns.user_id, ns.auth_token), verify=False)
            if response.status_code != 200:
                print('Ошибка при получении данных пользователя, код ответа {}'.format(response.status_code))
                print(response.text)
                quit()
            else:
                response_json_result = response.json()['result']
                roles = response_json_result['team_member.roles']['roles']
                if len({'users', 'tours'} & set(roles)) == 2 or 'super' in roles:
                    print('Запускаем процесс!')
                else:
                    print('У Вас недостаточно прав!')
                    quit()
        except (ReadTimeout, ConnectionError) as e:
                print(repr(e))

    @classmethod
    def get_remote_tour_params(cls, jurisdiction, remote_tour_id, auth_token):
        try:
            response = requests.get('https://{}/api/v3/tours/{}?client=site.admin&client_version=1.0&auth_token={}&'
                                    'fields=user_id,folder_id,title,hidden,preview,screen,baseurls,meta,'
                                    'footage.meta,footage.type,footage.status'
                                    .format(cls.JURISDICTIONS_HOSTS[jurisdiction]['host'], remote_tour_id, auth_token),
                                    verify=False)

            if response.status_code == 200:
                response_json_result = response.json()['result']
                return {
                    'tour_user_id': response_json_result['user_id'],
                    'tour_folder_id': response_json_result.get('folder_id', None),
                    'tour_title': response_json_result.get('title', None),
                    'tour_hidden': response_json_result['hidden'],
                    'tour_preview': response_json_result.get('preview', '').replace('/assets/', ''),
                    'tour_screen': response_json_result.get('screen', '').replace('/assets/', ''),
                    'tour_meta': response_json_result['meta'],
                    'tour_baseurl': response_json_result['tour_baseurl']
                        .replace('/assets/', '').replace(cls.JURISDICTIONS_HOSTS[jurisdiction]['url'], ''),
                    'footage_meta': response_json_result['footage']['meta'],
                    'footage_type': response_json_result['footage']['type'],
                    'footage_status': response_json_result['footage']['status'],
                    'footage_baseurl': response_json_result['footage_baseurl']
                        .replace('/assets/', '').replace(cls.JURISDICTIONS_HOSTS[jurisdiction]['url'], ''),
                }
            else:
                print('Ошибка при получении данных тура, код ответа {}'.format(response.status_code))
                print(response.text)
                quit()
        except (ReadTimeout, ConnectionError) as e:
                print(repr(e))

    @classmethod
    def get_tour_user_info(cls, jurisdiction, auth_token, tour_user_id):
        try:
            response = requests.get('https://{}/api/users.getBadges?client=site.admin&client_version=1.0&'
                                    'auth_token={}&v=2.0'.format(cls.JURISDICTIONS_HOSTS[jurisdiction]['host'],
                                                                 auth_token), verify=False)
            if response.status_code != 200:
                print('Ошибка при получении данных владельца тура, код ответа {}'.format(response.status_code))
                print(response.text)
                quit()
            else:
                response_json = response.json()
                for user in response_json:
                    if user['id'] == tour_user_id:
                        return {
                            'tour_user_email': user['email'],
                            'tour_user_name': user['name'],
                        }
        except (ReadTimeout, ConnectionError) as e:
                print(repr(e))

    @classmethod
    def get_tour_folder_title(cls, jurisdiction, auth_token, tour_user_id, tour_folder_id):
        tour_folder_title = None
        try:
            response = requests.get('https://{}/api/users.getFolders?user_id={}&client=site.admin&client_version=1.0&'
                                    'auth_token={}&v=2.0'.format(cls.JURISDICTIONS_HOSTS[jurisdiction]['host'],
                                                                 tour_user_id, auth_token), verify=False)
            if response.status_code != 200:
                print('Ошибка при получении данных папки, код ответа {}'.format(response.status_code))
                print(response.text)
                quit()
            else:
                response_json = response.json()
                for folder in response_json:
                    if folder['id'] == tour_folder_id:
                        tour_folder_title = folder['title']
                        break
                else:
                    tour_folder_title = None
        except (ReadTimeout, ConnectionError) as e:
                print(repr(e))

        return tour_folder_title

    @classmethod
    def create_tour(cls, jurisdiction, ns):
        # Проверяем пользователя - нет создаем
        user = User.query.filter(db.func.lower(User.email) == ns.tour_user_email).first()
        if not user:
            folder = None
            new_user = User(
                email=ns.tour_user_email,
                name=ns.tour_user_name,
                password_hash=User.hash_password('tmpPass%1.'),
                email_notifications=0,
                email_confirmed=False
            )
            db.session.add(new_user)
            db.session.commit()
            folder_user_id = new_user.id
            print('Юзер с именем: {} и email: {} создан'.format(new_user.name, new_user.email))
        else:
            # Проверяем папку тура
            folder = Folder.query.filter(Folder.title==ns.tour_folder_title, Folder.user_id==user.id).first()
            folder_user_id = user.id

        if not folder and ns.tour_folder_id:
            folder = Folder(user_id=folder_user_id, title=ns.tour_folder_title)
            db.session.add(folder)
            db.session.commit()

        new_footage = Footage(
            type=ns.footage_type,
            _status=ns.footage_status,
            user_id=folder_user_id,
            meta=ns.footage_meta
        )
        db.session.add(new_footage)
        db.session.flush()

        new_footage.mkdir(True)
        cls.copy_via_ssh(ns.footage_baseurl, new_footage.files.abs_path, cls.JURISDICTIONS_HOSTS[jurisdiction])

        new_tour = Tour(
            folder_id= folder.id if ns.tour_folder_id else None,
            footage_id=new_footage.id,
            user_id=folder_user_id,
            title=ns.tour_title,
            hidden=ns.tour_hidden,
            meta=ns.tour_meta
        )

        db.session.add(new_tour)
        db.session.flush()

        if ns.tour_preview:
            tour_preview_file_path = os.path.join(cls.LOCAL_ASSET_STORAGE_ROOT, ns.tour_preview)
            tour_preview_folder_path = os.path.split(os.path.abspath(tour_preview_file_path))[0]
            os.makedirs(tour_preview_folder_path, exist_ok=True)

            cls.copy_via_ssh(ns.tour_preview, tour_preview_file_path,
                             cls.JURISDICTIONS_HOSTS[jurisdiction], False)
            new_tour.preview = tour_preview_file_path
        if ns.tour_screen:
            tour_screen_file_path = os.path.join(cls.LOCAL_ASSET_STORAGE_ROOT, ns.tour_screen)
            tour_screen_folder_path = os.path.split(os.path.abspath(tour_screen_file_path))[0]
            os.makedirs(tour_screen_folder_path, exist_ok=True)

            cls.copy_via_ssh(ns.tour_screen, tour_screen_file_path,
                             cls.JURISDICTIONS_HOSTS[jurisdiction], False)
            new_tour.screen = tour_screen_file_path

        new_tour.mkdir()
        if ns.tour_baseurl:
            cls.copy_via_ssh(ns.tour_baseurl, new_tour.files.abs_path, cls.JURISDICTIONS_HOSTS[jurisdiction])

        db.session.commit()
        return new_tour.id

    @classmethod
    def persist_jurisdiction_changes(cls, jurisdiction, auth_token, remote_tour_id, new_tour_id):
        try:
            response = requests.post('https://{}/api/v3/tours/changed_jurisdiction?client=site.admin&client_version=1.0'
                                     '&auth_token={}'.format(cls.JURISDICTIONS_HOSTS[jurisdiction]['host'], auth_token),
                                     data=json.dumps({'local_id': remote_tour_id, 'remote_id': new_tour_id,
                                                      'moved_to': cls.LOCAL_JURISDICTION}),
                                     headers={'Content-type': 'application/json'}, verify=False)

            if response.status_code != 200:
                print('Ошибка при изменении юрисдикций тура на удаленной машине, код ответа {}'
                      .format(response.status_code))
                print(response.text)
        except (ReadTimeout, ConnectionError) as e:
                print(repr(e))

    @classmethod
    def delete_tour(cls, jurisdiction, remote_tour_id, auth_token):
        try:
            response = requests.delete('https://{}/api/v3/tours/{}?client=site.admin&client_version=1.0&auth_token={}'
                                       .format(cls.JURISDICTIONS_HOSTS[jurisdiction]['host'], remote_tour_id, auth_token),
                                        verify=False)

            if response.status_code != 204:
                print('Ошибка при удалении тура на удаленной машине, код ответа {}'
                      .format(response.status_code))
                print(response.text)
        except (ReadTimeout, ConnectionError) as e:
                print(repr(e))


