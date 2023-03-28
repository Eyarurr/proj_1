"""
Проходится по всем моделям и печатает статистику про их модели
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from statistics import mean, median
import traceback
from visual import create_app
from visual.models import Footage
from visual.util import ModelInfo

app = create_app('config.local.py')


with app.app_context():
    if len(sys.argv) > 1:
        footages = [Footage.query.get(sys.argv[1])]
    else:
        footages = Footage.query.filter(Footage.type == 'virtual', Footage._status.in_(['testing', 'published'])).order_by(Footage.id.desc()).limit(1000).all()
    total_footages = 0
    faces = []
    areas = []
    volumes = []
    densities = []
    for f in footages:
        mi = ModelInfo()
        try:
            mi.scan_file(f.in_files(f.meta.get('model')))
        except:
            print('ScanInfo failed for footage {}'.format(f.id))
            traceback.print_exc()
            continue
        if len(sys.argv) > 1:
            mi.digest()
        if mi.volume < 0.001:
            continue
        print('{}: faces: {}, A={:.2f} V={:.2f} F/m3 = {:.4f}'.format(f.id, mi.cnt_faces, mi.area, mi.volume, mi.cnt_faces / mi.volume))
        total_footages += 1
        faces.append(mi.cnt_faces)
        areas.append(mi.area)
        volumes.append(mi.volume)
        densities.append(mi.cnt_faces / mi.volume)

    print('AGGREGATION min-max: median/avg:')
    print('Faces:   {}-{}: {:.1f} / {}'.format(min(faces), max(faces), median(faces), mean(faces)))
    print('Area:    {:.1f}-{:.1f}: {:.1f} / {:.1f}'.format(min(areas), max(areas), median(areas), mean(areas)))
    print('Volume:  {:.1f}-{:.1f}: {:.1f} / {:.1f}'.format(min(volumes), max(volumes), median(volumes), mean(volumes)))
    print('Density: {:.1f}-{:.1f}: {:.1f} / {:.1f}'.format(min(densities), max(densities), median(densities), mean(densities)))
