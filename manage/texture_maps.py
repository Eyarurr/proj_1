import os
import time

from PIL import Image
from visual.models import Footage


def read_mtlfile(fname):
    materials = {}
    try:
        with open(fname) as f:
            lines = f.read().splitlines()
        for line in lines:
            if line:
                split_line = line.strip().split(' ', 1)
                if len(split_line) < 2:
                    continue

                prefix, data = split_line[0], split_line[1]
                if 'newmtl' in prefix:
                    material = {}
                    materials[data] = material
                elif materials:
                    if data:
                        split_data = data.strip().split(' ')

                        try:
                            if len(split_data) > 1:
                                material[prefix] = tuple(float(d) for d in split_data)
                            else:
                                try:
                                    material[prefix] = int(data)
                                except ValueError:
                                    material[prefix] = str(data)
                        except ValueError:
                            print('\tERROR: error reading %s' % os.path.split(fname)[1])
    except FileNotFoundError:
        print('\tERROR: %s' % 'MTL file NOT FOUND!')

    return materials


class TextureMaps:
    """Определение размеров текстурных карт"""
    def run(self, footage_ids, types, skip_no_mtl):
        types = list(types.split(','))

        if not set(types) & {'real', 'virtual'}:
            print('\033[31m Wrong footage types format!!!\033[0m')
            return

        q = Footage.query.filter(Footage.type.in_(types))

        if footage_ids not in ('all', ):
            try:
                footage_id = int(footage_ids)
                q = q.filter(Footage.id == footage_id)
            except ValueError:
                try:
                    between = list(map(int, footage_ids.split('-')))
                    between.sort()
                    q = q.filter(Footage.id.between(between[0], between[1]))
                except ValueError:
                    print('\033[31m Wrong footage ids format!!! \033[0m')
                    return

        footages = q.order_by(Footage.id.desc()).all()
        if len(footages) == 0:
            print('\033[31m Wrong footages found\033[0m')
            return

        for footage in footages:
            if 'mtl' not in footage.meta:
                if not skip_no_mtl:
                    print('Footage %d: ' % footage.id, 'no MTL in meta')
                continue

            textures = []

            print('Footage %d: ' % footage.id,
                  'obj=%s, ' % os.path.split(footage.meta.get('model'))[1],
                  'mtl=%s, ' % os.path.split(footage.meta.get('mtl'))[1],
                  )

            fname = footage.in_files(footage.meta['mtl'])
            materials = read_mtlfile(fname)

            for k, v in materials.items():
                for t_type in ('map_Ka', 'map_Kd', 'map_Ks'):
                    if v.get(t_type):
                        textures.append(v.get(t_type))

            for texture in list(set(textures)):
                t_file = footage.in_files('models', texture)

                try:
                    with Image.open(t_file) as im:
                        w, h = im.size
                        print('\t', texture, '\t', '%dx%dpx' % (w, h))
                except FileNotFoundError:
                    print('\tERROR: ', texture, '\t', 'NOT FOUND!')

            time.sleep(0.1)
