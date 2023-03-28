#!/usr/bin/env python

import colors
import click

from visual import create_app
from manage import *


if __name__ == "__main__":
    app = create_app('config.local.py')


    @app.cli.command()
    def runserver():
        print(colors.bold('Сервер больше так на запускается.\nСкажите ' + colors.green('./runserver.sh')))


    @app.cli.command('calc-model-sizes')
    def calc_model_sizes():
        CalcModelSizes().run()


    @app.cli.command('calc-passways')
    @click.option('--footage_id', help='ID съёмки.', required=True)
    @click.argument('footage_id')
    @click.option('--no-recalc', help='Не считать passways, если они уже есть.', is_flag=True, default=None)
    @click.option('--compare', help='Сравнить существующий граф с записанным, в базу не писать.', is_flag=True, default=None)
    @click.option('--quiet', '-q', help='Молча.', is_flag=True)
    def calc_passways(footage_id, no_recalc, compare, quiet):
        CalcPassways().run(footage_id, no_recalc, compare, quiet)


    @app.cli.command('update-geo-data')
    def update_geo_data():
        UpdateGeoData().run()


    @app.cli.command('set-option')
    @click.option('--tours', '-t', type=str, help='IDs туров')
    @click.option('--users', '-u', type=str, help='IDs пользователей')
    @click.option('--options', help='Опции. Через пробел fov=80 ...', required=True, multiple=True)
    @click.argument('options', nargs=-1)
    def set_option(tours, users, options):
        SetOption().run(tours, users, options)


    @app.cli.command('calc-skybox-sizes')
    @click.option('--footage_id', help='Идентификаторы съемки через пробел или "all".', required=True, multiple=True)
    @click.argument('footage_id', nargs=-1)
    @click.option('--loglevel', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], case_sensitive=False),
                  default='WARNING', help='Log Level')
    @click.option('--dry', is_flag=True, help='Dry run')
    def calc_skybox_sizes(**options):
        CalcSkyboxSizes().run(**options)


    @app.cli.command('check-clickable')
    @click.option('--user_id', '-u', help='ID юзера')
    @click.option('--tour_id', '-t', help='ID тура')
    def check_clickable(user_id, tour_id):
        CheckClickable().run(user_id, tour_id)


    @app.cli.command('copy-tour')
    @click.option('--tour_id', help='ID тура', required=True)
    @click.argument('tour_id')
    @click.option('--title', help='Название нового тура', required=True)
    @click.argument('title')
    @click.option('--folder_id', help='В какую папку скопировать. 0 — копировать в корневую, не указано — копировать в ту же.')
    @click.option('--copy-footage', help='Копировать съёмку', is_flag=True)
    @click.option('--copy-meta', help='Копировать мету', is_flag=True)
    @click.option('--created-by', help='created_by нового тура и съёмки')
    @click.option('--quiet', '-q', help='Молча', is_flag=True)
    def copy_tour(tour_id, title, folder_id, copy_footage, copy_meta, created_by, quiet):
        CopyTour().run(tour_id, title, folder_id, copy_footage, copy_meta, created_by, quiet)


    @app.cli.command('team-member-create')
    @click.option('--roles', help='Роли, через запятую', required=True)
    @click.argument('roles')
    @click.option('--email', help='E-mail', required=True)
    @click.argument('email')
    @click.option('--password', help='Пароль. Если указать "-", то будет создан пользователь без права авотризации паролем.',
                  required=True)
    @click.argument('password')
    def team_member_create(roles, email, password):
        TeamMemberCreate().run(roles, email, password)


    @app.cli.command('texture-maps')
    @click.option('--footage_ids', help='Please type Footage ID or Footage IDs range or all', required=True)
    @click.argument('footage_ids')
    @click.option('--types', '-t', default = 'real,virtual', help = 'Footage type (default: real,virtual)')
    @click.option('--skip-no-mtl', help='Do not report footages without MTL', is_flag=True)
    def texture_maps(footage_ids, types, skip_no_mtl):
        TextureMaps().run(footage_ids, types, skip_no_mtl)


    @app.cli.command('refill-trial-users')
    def refill_trial_users():
        RefillTrialUsers().run()


    @app.cli.command('explore-meta')
    @click.option('--what', type=click.Choice(['tours', 'footages']), help='Туры или съёмки', required=True)
    @click.argument('what')
    @click.option('--ids', help='all|id1,id2,id3|idA-idB', required=True)
    @click.argument('ids')
    @click.option('--property', '-p', help='Исследуемое свойство меты. Для словарей типа {id: Class, ...} '
                                           '(напр., скайбоксы), укажите skyboxes.*. Для списков [Class, ...] - walk[]')
    @click.option('--types', help='список из virtual, real, outside')
    @click.option('--statuses', help='список из loading, processing, testing, published, banned')
    @click.option('--limit', help='Лимит количества записей')
    @click.option('--values', is_flag=True, help='Показать значения')
    def explore_meta(**options):
        ExploreMeta().run(**options)


    @app.cli.command('autowalk')
    @click.option('--tour_id', help='ID тура.', required=True)
    @click.argument('tour_id')
    @click.option('--overwrite', help='Переписывать маршрут, если он уже есть.', is_flag=True)
    @click.option('--delay', help='Длительность задержки в точке, в секундах.', type=int, default=1)
    def autowalk(tour_id, overwrite, delay):
        AutoWalk().run(tour_id, overwrite, delay)


    @app.cli.command('acquire-tours')
    @click.option('--jurisdiction', help='Юрисдикция тура', required=True)
    @click.argument('jurisdiction')
    @click.option('--remote-tour-id', help='ID тура который переносится')
    @click.option('--remote-folder-id', help='ID папки которая переносится')
    @click.option('--remote-user-id', help='ID юзера, туры которого переносятся')
    def acquire_tours(jurisdiction, remote_tour_id, remote_folder_id, remote_user_id):
        AcquireTours().run(jurisdiction, remote_tour_id, remote_folder_id, remote_user_id)


    @app.cli.command('acquire-multitours')
    @click.option('--jurisdiction', help='Юрисдикция тура', required=True)
    @click.argument('jurisdiction')
    @click.option('--remote-multitour-id', help='ID мультитура который переносится')
    @click.option('--remote-folder-id', help='ID папки к которой привязан мультитур и которая переносится')
    @click.option('--remote-user-id', help='ID юзера, мультитуры которого переносятся')
    def acquire_multitours(jurisdiction, remote_multitour_id, remote_folder_id, remote_user_id):
        AcquireMultitours().run(jurisdiction, remote_multitour_id, remote_folder_id, remote_user_id)


    @app.cli.command('create-auth-token')
    @click.option('--email', help='E-mail юзера', required=True)
    @click.argument('email')
    @click.option('--expires', help='Дата смерти токена, YYYY-MM-DDTHH:MM:SS. По умолчанию — 3 месяца от текущего времени.')
    @click.option('--title', help='Название токена')
    def create_auth_token(email, expires, title):
        CreateAuthToken().run(email, expires, title)


    @app.cli.command('gen-datasets')
    @click.option('--user_email', help='E-mail юзера', required=True)
    @click.argument('user_email')
    @click.option('--clear', help='Сначала стереть все датасеты юзера.', is_flag=True)
    def gen_datasets(user_email, clear):
        GenerateDatasets().run(user_email, clear)


    @app.cli.command('rpdsh')
    @click.option('--user_email', help='E-mail юзера', required=True)
    @click.argument('user_email')
    @click.option('--dataset_id', default=None)
    @click.option('--clear', help='Сначала стереть все датасеты юзера.', is_flag=True)
    def rpdsh(user_email, dataset_id, clear):
        RemoteProcessingShell().run(user_email, dataset_id, clear)


    # Обслуживание статистики
    @app.cli.command('stat-aggregate')
    @click.option('--updated_tables', default=['count', 'time', 'city', 'referer'], required=True, multiple=True,
                  help='tables to update (count, time, city, referer) "./py.py stat-aggregate count city"')
    @click.argument('updated_tables', nargs=-1)
    @click.option('--tour-ids', '-t', help='Aggregate only this tour ids (example "505, 506, 234")')
    @click.option('--folder-id', '-e', help='Aggregate only this folder')
    @click.option('--user-id', '-uid', help='Aggregate only this user')
    @click.option('--user-email', '-m', help='Aggregate only this user')
    @click.option('--interval', '-i', help='2020-01-01...2020-02-01', required=True)
    def stat_aggregate(updated_tables, tour_ids, folder_id, user_id, user_email, interval):
        StatAggregate().run(updated_tables, tour_ids, folder_id, user_id, user_email, interval)


    @app.cli.command('stat-update')
    @click.option('--updated_tables', default=['count', 'time', 'city', 'referer'], required=True, multiple=True,
                  help='tables to update (count, time, city, referer) "./py.py stat-update count city"')
    @click.argument('updated_tables', nargs=-1)
    def stat_update(updated_tables):
        StatUpdate().run(updated_tables)


    @app.cli.command('stat-delete')
    def stat_delete():
        StatDelete().run()


    @app.cli.command('stat-demo')
    @click.option('--user_email', help='E-mail юзера', required=True)
    @click.argument('user_email')
    @click.option('--from-date', '-f', help='Дата начала заполнения', required=True)
    @click.option('--to-date', '-t', help='Дата конца заполнения', required=True)
    @click.option('--quiet', '-q', is_flag=True, help='Режим без вывода в консоль')
    def stat_demo(user_email, from_date, to_date, quiet):
        StatDemo().run(user_email, from_date, to_date, quiet)


    @app.cli.command('stat-recount')
    def stat_recount():
        StatRecount().run()


    @app.cli.command('stat-zero')
    def stat_zero():
        StatZero().run()


    # Чистка и напоминания
    @app.cli.command('purgatory-footages')
    @click.option('--loglevel', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], case_sensitive=False),
                  default='WARNING', help='Log Level')
    @click.option('--dry', is_flag=True, help='Dry run')
    def purgatory_footages(loglevel, dry):
        PurgeFootages().run(loglevel, dry)


    @app.cli.command('ressurect-footage')
    @click.option('--footage_id', help='ID съёмки.', required=True)
    @click.argument('footage_id')
    def ressurect_footage(footage_id):
        RessurectFootage().run(footage_id)


    @app.cli.command('clean-models')
    @click.option('--before', '-b', type=int, default=0, help='Для съёмок, созданных более этого количества дней, включительно')
    @click.option('--after', '-a', type=int, default=0, help='Для съёмок, созданных менее этого количества дней, включительно')
    @click.option('--dry', '-d', is_flag=True, help='Dry run')
    def clean_models(before, after, dry):
        CleanModels().run(before, after, dry)


    @app.cli.command('footage-expire')
    @click.option('--quiet', '-q', is_flag=True, help='Тихий режим, для запуска фонового задания')
    @click.option('--dry', is_flag=True, help='Dry run, не трогать базу, только писать, что произойдёт')
    @click.option('--loglevel', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], case_sensitive=False),
                  default='WARNING', help='Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL')
    def footage_expire(quiet, dry, loglevel):
        with app.app_context():
            with app.test_request_context():
                FootageExpire().run(quiet, dry, loglevel)


    @app.cli.command('purge-deleted-users')
    @click.option('--dry', is_flag=True, help='Dry run, не трогать базу, только писать, что произойдёт')
    @click.option('--nomail', is_flag=True, help='Не слать писем')
    @click.option('--loglevel', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], case_sensitive=False),
                  default='WARNING', help='Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL')
    def purge_deleted_users(dry, nomail, loglevel):
        with app.app_context():
            PurgeDeletedUsers().run(dry, nomail, loglevel)


    @app.cli.command('clean-unconfirmed-users')
    @click.option('--loglevel', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], case_sensitive=False),
                  default='WARNING', help='Log Level')
    @click.option('--dry', is_flag=True, help='Dry run')
    def clean_unconfirmed_users(loglevel, dry):
        CleanUnconfirmedUsers().run(loglevel, dry)


    @app.cli.command('branding-expire')
    @click.option('--quiet', '-q', is_flag=True, help='Тихий режим, для запуска фонового задания')
    @click.option('--dry', is_flag=True, help='Dry run, не рассылать письма, только писать, что произойдёт')
    @click.option('--loglevel', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], case_sensitive=False),
                  default='WARNING', help='Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL')
    def branding_expire(quiet, dry, loglevel):
        with app.app_context():
            with app.test_request_context():
                BrandingExpire().run(quiet, dry, loglevel)


    # Сборка туров из исходников (скармливается директория с исходниками, все свойства тура — через командную строку
    @app.cli.command('create-tour-inside')
    @click.option('--sources_dir', help='Директория с исходниками', required=True)
    @click.argument('sources_dir')
    @click.option('--user_id', type=int, help='ID юзера, будущего хозяина тура', required=True)
    @click.argument('user_id')
    @click.option('--tour_title', help='Название тура', required=True)
    @click.argument('tour_title')
    @click.option('--model', help='Путь к модели относительно <sources_dir>', default='highpoly.obj')
    @click.option('--model-lowpoly', is_flag=True, help='Нужно ли низкополигонализировать модель')
    @click.option('--coords-file', help='JSON или TXT с координатами. В противном случае берутся из модели')
    @click.option('--panoramas-dir', help='Путь к панорамам (колбасам) относительно <sources_dir>', default='panoramas')
    @click.option('--panoramas-binocular', help='Путь к бинокулярным панорамам (колбасам) относительно <sources_dir>')
    @click.option('--panoramas-type', type=click.Choice(['vray', 'corona']), help='Тип рендера', default='vray')
    @click.option('--tour-type', type=click.Choice(['virtual', 'real']), help='Тип тура', default='virtual')
    @click.option('--profile-time', is_flag=True, help='Профилировать время на разные этапы')
    @click.option('--skip-build', is_flag=True, help='Не собирать, только собрать в loading')
    @click.option('--dry', is_flag=True, help='Ничего не копировать; для отладки')
    def create_tour_inside(sources_dir, user_id, tour_title, **kwargs):
        CreateTourInside().run(sources_dir, user_id, tour_title, **kwargs)


    @app.cli.command('create-tour-outside')
    @click.option('--sources_dir', help='Директории с исходниками', required=True)
    @click.argument('sources_dir')
    @click.option('--target_zip', help='Как назвать ZIP-файл с туром', required=True)
    @click.argument('target_zip')
    @click.option('--resolutions', help='Список разрешений через запятую: W1xH1,W2xH2,...',
                  default='480x480,720x720,1080x1080,1200x1200,1540x1540')
    def create_tour_outside(sources_dir, target_zip, resolutions):
        CreateTourOutside().run(sources_dir, target_zip, resolutions)


    # Сборка тура из loading -> testing
    @app.cli.command('build-tour-inside')
    @click.option('--tour_id', type=int, help='ID тура', required=True)
    @click.argument('tour_id')
    @click.option('--profile-time', is_flag=True, help='Профилировать время на разные этапы')
    def build_tour_inside(tour_id, **kwargs):
        BuildTourInside().run(tour_id, **kwargs)


    @app.cli.command('build-tour-outside')
    @click.option('--tour_id', type=int, help='ID тура', required=True)
    @click.argument('tour_id')
    @click.option('--quiet', '-q', is_flag=True, help='Тихий режим, для запуска фонового задания')
    def build_tour_outside(tour_id, quiet):
        BuildTourOutside().run(tour_id, quiet)


    app.cli()
