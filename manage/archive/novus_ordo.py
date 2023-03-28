import colors

from flask_script import Command

from visual.models import *
from visual.core import db
from manage.archive import dam
from visual.util import Quaternion
from .progress import Progress


log = logging.getLogger(__name__)
log.setLevel(logging.WARNING)

progress = Progress()


def pprint(obj):
    print(json.dumps(obj, indent=4, ensure_ascii=False))




class NovusOrdoSecolorum(Command):
    def __init__(self, func=None):
        super().__init__(func)

    def run(self):
        # Пустая директория для инициализации ассетов
        emptydir = tempfile.mkdtemp()

        # Все 'real' туры с id <= 223 делаем 'legacy', если конвертер работает не впервые
        Tour.query.filter(Tour.id <= 223).update({'type': 'legacy'}, synchronize_session=False)
        db.session.commit()

        tours = Tour.query.order_by(Tour.id).all()
        progress.action('Конвертируем туры', len(tours))
        for tour in tours:
            try:
                c = TourConverter(tour)
                c.convert(emptydir)
                progress.step()
                db.session.commit()
            except:
                print(colors.red('Проблема с туром %r' % tour))
                raise

        os.rmdir(emptydir)

        progress.end()


class TourConverter:
    def __init__(self, tour):
        self.tour = tour
        self.meta = {
            'model': None,
            'model_format': None,
            'floors': None,
            'resolutions': None,
            'skyboxes': None,
            'start': None
        }
        self.model_json = None

    def convert(self, emptydir):
        # print(colors.black('Converting tour %r: %r -> %r' % (self.tour, self.tour.tour, self.tour.files)))

        # Удаляем tour.files и создаём заново пустую директорию
        del self.tour.files
        self.tour.files = emptydir

        # Читаем model.json
        os.chdir(self.tour.tour.abs_path)
        with open('model.json') as fp:
            self.model_json = json.load(fp)

        self.convert_model()
        self.convert_floors()
        self.convert_skyboxes()

        self.tour.meta = self.meta
        if self.tour.footage.type == 'legacy':
            self.tour.footage.type = 'real'

    def convert_model(self):
        models_dir = os.path.join(self.tour.files.abs_path, 'models')
        os.mkdir(models_dir)

        model_format = self.model_json.get('options', {}).get('format', 'obj')
        uuid = self.model_json['job']['uuid']

        # Копируем/конвертируем модель
        if model_format == 'obj':
            src = '%(uuid)s_obj/%(uuid)s.obj' % {'uuid': uuid}
            shutil.copy(src, os.path.join(self.tour.files.abs_path, 'models', 'model-0.obj'))
        else:
            mesh = dam.BinaryMesh('%(uuid)s_50k.dam/%(uuid)s_50k.dam' % {'uuid': uuid})
            mesh.save_obj_mtl(
                os.path.join(self.tour.files.abs_path, 'models', 'model-0.obj'),
                os.path.join(self.tour.files.abs_path, 'models', 'model-0.mtl')
            )
            self.meta['mtl'] = 'models/model-0.mtl'

        self.meta['model'] = 'models/model-0.obj'

        # Если есть, копируем текстуры
        textures = '%s_50k_texture_jpg_high' % uuid
        if os.path.isdir(textures):
            for fname in os.listdir(textures):
                shutil.copy(
                    os.path.join(textures, fname),
                    os.path.join(self.tour.files.abs_path, 'models', fname)
                )

        self.meta['model_format'] = 'obj'

    def convert_floors(self):
        maps_dir = os.path.join(self.tour.files.abs_path, 'maps')
        os.mkdir(maps_dir)

        self.meta['floors'] = {}
        for floor_id, floor in self.model_json['maps'].items():
            floor_id = int(floor_id)
            big_fname = '%d-big.%s' % (floor_id, floor['b'][-3:])
            small_fname = '%d-small.%s' % (floor_id, floor['m'][-3:])

            shutil.copy(floor['b'], os.path.join(maps_dir, big_fname))
            shutil.copy(floor['m'], os.path.join(maps_dir, small_fname))

            self.meta['floors'][floor_id] = {
                'small': 'maps/' + small_fname,
                'big': 'maps/' + big_fname
            }

    def convert_skyboxes(self):
        old_new = {}
        cur_id = 1

        # Разрешения
        if self.tour.type == 'legacy':
            pans_default = {'high': 1024, 'low': 256}
        elif self.tour.type == 'real':
            pans_default = {'high': 1280, 'low': 256}
        else:
            pans_default = {'high': 1540, 'low': 256}
        pans = self.model_json.get('pans', pans_default)

        self.meta['resolutions'] = [int(x) for x in pans.values()]
        for res in pans.values():
            os.mkdir(os.path.join(self.tour.files.abs_path, str(res)))

        faces = {
            'legacy': {0: 4, 1: 0, 2: 1, 3: 2, 4: 3, 5: 5},
            'virtual': dict(zip(range(6), range(6))),
            'real': dict(zip(range(6), range(6))),
        }

        # Конвертим скайбоксы
        self.meta['skyboxes'] = {}
        for sweep_id, sweep in self.model_json['sweeps'].items():
            old_new[sweep_id] = cur_id
            skybox = {}

            # position
            pos = sweep['position']
            skybox['pos'] = [pos['x'], pos['y'], pos['z']]

            # disabled
            if not sweep.get('enabled', True):
                skybox['disabled'] = True

            # q, floor
            q = Quaternion(sweep['quaternion'])
            if self.tour.footage.type == 'legacy':
                q = q * Quaternion(0, 0, 0.7071067811865476, 0.7071067811865476)
                q.y, q.z = -q.y, -q.z
                skybox['q'] = q.as_list()

                # У legacy-туров этажи были указаны неверно (всегда 1), не используем их.
            else:
                skybox['q'] = q.as_list()

                if 'floor' not in sweep or sweep['floor'] == '':
                    skybox['floor'] = list(self.meta['floors'].keys())[0]
                else:
                    skybox['floor'] = int(sweep['floor'])

            # title
            if 'name' in sweep and sweep['name'] != '':
                skybox['title'] = sweep['name']

            # floorY
            if 'floorY' in sweep:
                skybox['markerZ'] = sweep['floorY']

            # Копируем панорамы
            for pan_dir, pan_res in pans.items():
                for was, will in faces[self.tour.type].items():
                    shutil.copy(
                        os.path.join('pan', pan_dir, '%s_skybox%d.jpg' % (sweep_id, was)),
                        os.path.join(self.tour.files.abs_path, str(pan_res), '%d-%d.jpg' % (cur_id, will))
                    )

            self.meta['skyboxes'][cur_id] = skybox
            cur_id += 1

        # Стартовая точка
        self.meta['start'] = {
            'skybox': old_new[self.model_json['start']['sweep']]
        }
        q = Quaternion(self.model_json['start']['quaternion'])
        if self.tour.footage.type == 'legacy':
            q.y, q.z = q.z, q.y
            q *= Quaternion(0, 0.7071067811865476, 0, 0.7071067811865476)
        self.meta['start']['q'] = q.as_list()
