import os
import logging
import subprocess
import json

from PIL import Image
from visual.models import Footage
from visual.core import db
from sqlalchemy.orm.attributes import flag_modified

script_path = os.getcwd() + '/ephemera/fake_offset_scale/index.js'

footages = Footage.query.\
    filter(Footage.type=='virtual').\
    filter(Footage._status.in_(['published', 'testing'])).\
    order_by(Footage.id.desc()).\
    all()

for footage in footages:
    if 'model' not in footage.meta:
        print('Нет model в fotage.meta у съёмки {}'.format(footage.id))
        continue
    model_path = os.path.join(footage.files.abs_path, footage.meta['model'])
    big_map = footage.meta.get('floors', {}).get('1', {}).get('big')
    if big_map:
        map_path = footage.in_files(big_map)
        if not os.path.isfile(map_path):
            print('Нет картинки миникарты, footage_id: {}'.format(footage.id))
            continue
    else:
        continue
    if os.path.exists(model_path):
        pass
    else:
        print('Нет модели по указанному пути, footage_id: {}'.format(footage.id))
        continue
    worker = subprocess.run(
        [script_path, '-m', model_path, '-i', map_path],
        cwd=os.path.dirname(script_path),
        input=json.dumps(footage.meta),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    if worker.stderr == '':
        result = json.loads(worker.stdout)
        scale = result.get('scale', 100)
        offset = result.get('offset', [0, 0])
        for floor_id, floor in footage.meta.get('floors', {}).items():
            if floor_id:
                footage.meta['floors'][floor_id]['scale'] = scale
                footage.meta['floors'][floor_id]['offset'] = offset
        print('Съёмка {} успешно обработана: scale={}, offset={}'.format(footage.id, scale, offset))
    else:
        print('! Ошибка обработки съёмки {}'.format(footage.id))


