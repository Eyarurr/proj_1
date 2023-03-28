import os
import re
import shutil
import datetime
import tempfile
import traceback
import time
import json
import zipfile
from rq.job import Job

from flask import current_app as app
from sqlalchemy.orm.attributes import flag_modified

from .progress import Progress
from visual.core import db
from visual.util import downsize_img
from visual.models import Tour, Footage, User
from visual.bgjobs import BgJobState
from visual.jobs import TourInsideBuilder


class BuildTourInside:
    """Собирает тур. Ожидается, что тур в статусе loading, queued или testing, у него есть исходники в _loading.
    Если тур был в очереди, то из очереди он удаляется.
    При успешной сборке тур получает статус testing, при ошибках — loading.
    """
    def run(self, tour_id, **kwargs):
        self.options = kwargs
        tour_id = int(tour_id)

        tour = Tour.query.get(tour_id)

        if tour.footage.status not in ('loading', 'testing', 'queued'):
            print('Тур не в статусе loading, queued или testing, сборка невозможна.')
            return

        worker = TourInsideBuilder(tour)

        if tour.footage.status == 'queued':
            # Если тур был в очереди, то удаляем задачу из очереди и '_queued' из меты
            job_id = tour.footage.meta.get('_queued', {}).get('job_id')
            if job_id:
                job = Job.fetch(job_id)
                if job:
                    job.cancel()
                    print('Delete job {}'.format(job_id))
                else:
                    print('Job {} not found in queue'.format(job_id))
            tour.footage.meta.pop('_queued', None)

        tour.footage.status = 'processing'
        tour.footage.meta['_processing'] = {
            'since': datetime.datetime.now().isoformat()
        }
        flag_modified(tour.footage, 'meta')
        db.session.commit()

        t1 = time.time()
        try:
            result = worker.run()
        except Exception as e:
            traceback.print_exc()
            result = False

        elapsed = time.time() - t1
        if self.options['profile_time']:
            print('Сборка тура заняла {:0>2}:{:0>2}'.format(int(elapsed) // 60, int(elapsed) % 60))

        if result:
            print('Тур успешно собрался.')
            tour.footage.status = 'testing'
        else:
            print('При сборке тура произошли ошибки:')
            print('\n'.join(tour.footage.meta.get('_loading', {}).get('build_errors', [])))
            tour.footage.status = 'loading'

        tour.footage.meta.pop('_processing', None)
        flag_modified(tour.footage, 'meta')
        db.session.commit()


class BuildTourOutside:
    """Собирает outside-тур в статусе loading.
    """
    def run(self, tour_id, quiet=False):
        tour_id = int(tour_id)
        self.quiet = quiet
        self.bgstate = BgJobState('tour_build', tour_id, 'processing')
        self.progress = Progress(quiet=self.quiet)

        try:
            if not self.load_tour(tour_id):
                return False

            self.tour.footage.status = 'processing'
            db.session.commit()

            self.process_frames()

            self.tour.footage.status = 'testing'
            db.session.commit()

            self.progress.end()
            self.bgstate.done()
        except (Exception, KeyboardInterrupt) as e:
            self.bgstate.error('Сборщик упал: {}'.format(str(e)))
            raise

        return True

    def load_tour(self, tour_id):
        """Загружает тур в self.tour и проверяет возможность сборки. Если тур собрать нельзя,
        то устанавливает ошибку в self.bgstate и возвращает False"""
        self.tour = Tour.query.get(tour_id)
        if not self.tour:
            self.bgstate.error("Тур id={} не найден для сборки!".format(tour_id))
            app.logger.error("Тур id={} не найден для сборки!".format(tour_id))
            return False

        footage = self.tour.footage
        meta = footage.meta

        if footage.status != 'loading':
            self.bgstate.error("Тур id={} имеет статус {}, а не loading".format(self.tour.id, self.tour.footage.status))
            app.logger.error("Тур id={} имеет статус {}, а не loading".format(self.tour.id, self.tour.footage.status))
            return False

        if footage.type != 'outside':
            self.bgstate.error('Тур id={} не является outside-туром, а имеет тип {}'.format(self.tour.id, self.tour.footage.type))
            app.logger.error('Тур id={} не является outside-туром, а имеет тип {}'.format(self.tour.id, self.tour.footage.type))

        if meta.get('problems'):
            self.bgstate.error("Тур id={} имеет нерешённые проблемы ({} шт), поэтому его собрать нельзя".format(self.tour.id, len(meta['problems'])))
            app.logger.error("Тур id={} имеет нерешённые проблемы ({} шт), поэтому его собрать нельзя".format(self.tour.id, len(meta['problems'])))
            return False

        return True

    def process_frames(self):
        """Уменьшает фреймы."""
        footage = self.tour.footage
        meta = footage.meta

        # Общее количество фреймов
        cnt_frames = 0
        for set_ in meta['sets'].values():
            cnt_frames += len(set_['frames'])

        self.progress.action('Создаются фреймы', cnt_frames)

        for set_ in meta['sets'].values():
            for res in meta['resolutions']:
                os.makedirs(self.tour.footage.in_files('frames', str(set_['id']), 'x'.join([str(_) for _ in res])), exist_ok=True)

            for frame_id, frame in set_['frames'].items():
                self.bgstate.wtf = 'Создаётся фрейм {} в сете {}'.format(frame_id, set_['id'])
                for res in meta['resolutions']:
                    downsize_img(
                        footage.in_files('frames', str(set_['id']), frame['filename']),
                        footage.in_files('frames', str(set_['id']), 'x'.join([str(_) for _ in res]), '{}.jpg'.format(frame_id)),
                        res,
                        'crop'
                    )

                self.progress.step()
                self.bgstate.complete = self.progress.cnt_step / self.progress.cnt_total


class CreateTourInside:
    """
    Создаёт из исходников в указанной директории тур в статусе 'loading' и отправляет его на сборку через
    TourBuilder. Во время сборки туру присваивается статус 'processing', после успешной сборки — 'testing',
    после безуспешной — 'loading'.

    ./py.py create-tour-inside [OPTIONS] <sources_dir> <user_id> <tour_title>

    <sources_dir> — путь к директории с исходниками: модель, колбасы, возможно — файл с координатами.
    <user_id> — какому юзеру сделать тур
    <tour_title> — название тура

    options:
    --model=highpoly.obj            Путь к модели относительно <sources_dir>
    --model-lowpoly                 Нужно ли низкополигонализировать модель
    --coords-file                   JSON или TXT с координатами. В противном случае берутся из модели.
    --panoramas-dir=panoramas       Путь к панорамам (колбасам) относительно <sources_dir>
    --panoramas-binocular           Путь к бинокулярным панорамам относительно <sources_dir>
    --panoramas-type=vray           Тип рендера панорам (vray, corona)
    --tour-type=virtual             Тип съёмки (virtual, real)
    --profile-time                  Профилировать время на разные этапы
    --skip-build                    Не собирать, только собрать в loading
    """
    def run(self, sources_dir, user_id, tour_title, **kwargs):
        self.sources_dir = sources_dir
        self.options = kwargs

        if not os.path.exists(sources_dir):
            print('Не найдена директория {}'.format(sources_dir))
            return False

        user = User.query.get(user_id)
        if not user:
            print('Не найден User ID={}'.format(user_id))
            return False

        print('0. Создаём пустой тур и съёмку')
        self.footage = Footage(user_id=user.id, created_by=user.id, type=self.options['tour_type'], _status='loading')
        self.footage.meta = {
            '_loading': {
                'options': {}
            }
        }
        self.meta = self.footage.meta['_loading']
        db.session.add(self.footage)
        db.session.flush()
        self.footage.mkdir()
        os.makedirs(self.footage.in_files('_loading'), exist_ok=True)

        self.tour = Tour(user_id=user.id, footage_id=self.footage.id, footage=self.footage, title=tour_title)
        db.session.add(self.tour)

        # Сборка в loading
        t1 = time.time()
        print('1. Собираем тур в статусе loading')

        print('1.1. Копируем модель')
        if not self.copy_model():
            print('Не удалось скопировать модель')
            return False

        print('1.2. Копируем панорамы')
        if not self.copy_panoramas():
            print('Не удалось скопировать панорамы')
            return False

        print('1.3. Копируем координаты')
        if not self.copy_coords():
            print('Не удалось скопировать координаты')
            return False

        flag_modified(self.footage, 'meta')
        db.session.commit()

        elapsed = time.time() - t1
        if self.options['profile_time']:
            print('Запихивание исходников в тур в статусе loading заняло {:0>2}:{:0>2}'.format(int(elapsed) // 60,
                                                                                               int(elapsed) % 60))

        # Запуск TourBuilder
        if not self.options['skip_build']:
            t1 = time.time()
            print('2. Собираем тур')

            ok = self.process_tour()
            if not ok:
                print('При сборке тура произошли ошибки:')
                print('\n'.join(self.footage.meta.get('_loading', {}).get('build_errors', [])))

            elapsed = time.time() - t1
            if self.options['profile_time']:
                print('Сборка заняла {:0>2}:{:0>2}'.format(int(elapsed) // 60, int(elapsed) % 60))

    def copy_model(self):
        os.makedirs(self.footage.in_files('_loading', 'models'), exist_ok=True)
        src = os.path.join(self.sources_dir, self.options['model'])
        dst = self.footage.in_files('_loading', 'models', self.options['model'])

        if not self.options['dry']:
            shutil.copy(src, dst)

        self.meta['models'] = [{
            'file_name': self.options['model'],
            'size': os.stat(src).st_size
        }]

        if self.options['model_lowpoly']:
            self.meta['options']['model_lowpoly'] = True
        return True

    def copy_panoramas(self):
        self.meta['skyboxes'] = {}
        self.meta['options']['render_type'] = self.options['panoramas_type']
        src_dir = os.path.join(self.sources_dir, self.options['panoramas_dir'])
        dst_dir = self.footage.in_files('_loading', 'skyboxes')
        os.makedirs(dst_dir, exist_ok=True)

        for item in os.scandir(src_dir):
            r = re.search(r'(\d+)\.([^.]+)$', item.name, re.IGNORECASE)
            if not r:
                print('Непонятное имя файла панорамы: {}, пропускаем'.format(item.name))
                continue

            skybox_id = str(int(r.group(1)))
            ext = r.group(2).lower()

            # Проверяем расширение
            if ext not in ('jpg', 'jpeg', 'png'):
                print('Херовое расширение {} у файла {}, пропускаем'.format(ext, item.name))
                continue

            print('Копируем панораму {}: {}'.format(skybox_id, item.name))
            if not self.options['dry']:
                shutil.copy(item.path, dst_dir)

            self.meta['skyboxes'][skybox_id] = {
                'file_name': item.name,
                'file_size': item.stat().st_size
            }

        return True

    def copy_coords(self):
        if not self.options['coords_file']:
            self.meta['options']['coords_from_obj'] = True
            return True

        coords_file = os.path.join(self.sources_dir, self.options['coords_file'])
        coords_type = os.path.splitext(coords_file)[1].lower()
        if coords_type == '.txt':
            with open(coords_file) as fh:
                for line in fh:
                    line = line.strip()
                    r = re.search('^(\d+)\s+X=([-\d\.]+)\s+Y=([-\d\.]+)\s+Z=([-\d\.]+)\s+QX=([-\d\.]+)\s+QY=([-\d\.]+)\s+QZ=([-\d\.]+)\s+QW=([-\d\.]+)', line)
                    if not r:
                        print('Непонятная строка в файле с координатами: "{}"'.format(line))
                        continue

                    skybox_id = r.group(1)

                    if skybox_id not in self.meta['skyboxes']:
                        print('Ошибка: данные для скайбокса {} есть в файле с координатами, но такой панорамы нет.'.format(skybox_id))
                        return False

                    self.meta['skyboxes'][skybox_id]['pos'] = [float(r.group(x)) for x in range(2, 5)]
                    self.meta['skyboxes'][skybox_id]['q'] = [float(r.group(x)) for x in range(5, 9)]

        elif coords_type == '.json':
            with open(coords_file) as fh:
                coords = json.load(fh)
                for skybox_id, data in coords.items():
                    if skybox_id not in self.meta['skyboxes']:
                        print('Ошибка: данные для скайбокса {} есть в файле с координатами, но такой панорамы нет.'.format(skybox_id))
                        return False
                    self.meta['skyboxes'][skybox_id]['pos'] = data['pos']
                    self.meta['skyboxes'][skybox_id]['q'] = data['q']

        else:
            print('Непонятное расширение {} у файла с координатами {}'.format(coords_type, coords_file))
            return False

        return True

    def process_tour(self):
        if self.options['dry']:
            print('Сборщик был запущен с опцией --dry, хуй тут что соберёшь.')
            return False

        self.tour.footage._status = 'processing'
        self.tour.footage.meta['_processing'] = {
            'since': datetime.datetime.now().isoformat()
        }
        flag_modified(self.tour.footage, 'meta')
        db.session.commit()

        worker = TourInsideBuilder(self.tour)
        try:
            ok = worker.run()
        except Exception as e:
            traceback.print_exc()
            ok = False

        if ok:
            self.tour.footage._status = 'testing'
        else:
            self.tour.footage._status = 'loading'

        self.tour.footage.meta.pop('_processing', None)
        flag_modified(self.tour.footage, 'meta')
        db.session.commit()
        return ok


class CreateTourOutside:
    """
    Сборка outside-тура из исходников. Получает на вход директорию. В корне ищет файл с расширением .obj, его считает моделью.
    Каждую поддиректорию рассматривает как сет. В них скрипт ожидает увидеть файл coords.txt и .jpg или .png-файлы с фреймами.
    Собранный тур упаковывает в .zip, пригодный для загрузки через админку.
    """
    def run(self, source_dir, target_zip, resolutions):
        self.meta = {
            'sets': {}
        }
        self.set_id = 1

        with zipfile.ZipFile(target_zip, 'w') as zzz:
            # Разрешения
            self.meta['resolutions'] = []
            for res in resolutions.split(','):
                w, h = [int(_) for _ in res.split('x')]
                self.meta['resolutions'].append((w, h))

            # Сканируем директорию
            for item in os.scandir(source_dir):
                if item.is_dir():
                    if not os.path.isfile(os.path.join(source_dir, item.name, 'coords.txt')):
                        print('Нашёл директорию {}, но в ней нет coords.txt, пропускаем'.format(item.name))
                        continue

                    print('Нашёл директорию с сетом {}'.format(item.name))
                    if not self.add_set_dir(os.path.join(source_dir, item.name), zzz):
                        print('Тур не собрался.')
                        return
                elif item.name.lower().endswith('.obj'):
                    print('Нашёл модель: {}'.format(item.name))
                    self.meta['model'] = 'model-0.obj'
                    zzz.write(os.path.join(source_dir, item.name), 'model-0.obj', zipfile.ZIP_LZMA)

            # Пишем метадату в архив
            zzz.writestr('meta.json', json.dumps(self.meta, indent=4), zipfile.ZIP_LZMA)

        print('Готово, бля.')

    def add_set_dir(self, path, zzz):
        set = {
            'id': self.set_id,
            'name': path.split('/')[-1],
            'frames': {},
            'sort': self.set_id
        }

        # Читаем координаты
        coords = {}
        with open(os.path.join(path, 'coords.txt')) as fh:
            for line in fh:
                frame_id, pos, angle, fov = [_.strip() for _ in line.split(';')]
                coords[int(frame_id)] = {
                    'pos': [float(_) for _ in pos.split(',')],
                    'angle': [float(_) for _ in angle.split(',')],
                    'fov': float(fov)
                }

        for file in os.scandir(path):
            r = re.search('(\d+)\.[(jpg)|(png)|(jpeg)]', file.name.lower())
            if r is None:
                continue
            frame_id = int(r.group(1))

            if frame_id not in coords:
                print('    Нашёл фрейм {}, но в coords.txt нет координат для id={}'.format(file.name, frame_id))
                return False

            if file.name.lower().endswith('.jpg') or file.name.lower().endswith('.png'):
                print('    Нашёл фрейм {}, id={}, coords={}'.format(file.name, frame_id, coords[frame_id]))

                # Делаем все размеры
                for w, h in self.meta['resolutions']:
                    arcname = 'frames/{}/{}x{}/{}.jpg'.format(set['name'], w, h, frame_id)
                    with tempfile.NamedTemporaryFile(suffix='.jpg') as tmp:
                        print('        {} -> {}'.format(file.name, arcname, tmp.name))
                        downsize_img(os.path.join(path, file.name), tmp, (w, h), 'crop')
                        zzz.write(tmp.name, arcname)

                # Добавляем в set.frames
                set['frames'][frame_id] = coords[frame_id]

            elif file.name != 'coords.txt':
                print('    Левый файл {}, пропускаем'.format(file.name))

        self.meta['sets'][str(self.set_id)] = set
        self.set_id += 1

        return True
