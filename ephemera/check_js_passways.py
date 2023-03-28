import os
import json
import subprocess

from visual.models import Tour
from visual.core import db
from sqlalchemy.orm.attributes import flag_modified


def diff(old, new):
    s1 = set(map(tuple, old))
    s2 = set(map(tuple, new))
    sX = s1 ^ s2
    return sorted(list(sX), key=lambda x: int(x[0]))


def dict_to_binary(the_dict):
    str = json.dumps(the_dict)
    return bytes(str.encode('utf-8'))


tours = db.session.query(Tour). \
    filter(Tour.hidden == False). \
    order_by(Tour.id). \
    all()

for tour in tours:
    if tour.footage.type == 'virtual' and tour.footage.meta.get('passways', False):
        model_path = tour.footage.in_files(tour.footage.meta['model'])

        with subprocess.Popen(['./manage/passways/passways.js',
                               '--model',
                               model_path
                               ],
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as proc:
            proc.stdin.write(dict_to_binary(tour.footage.meta))
            output, err = proc.communicate()

        print('Tour id: {}'.format(tour.id))
        print('-------------------------------------------------------------')
        print(diff(tour.footage.meta['passways'], json.loads(output)))
        if err:
            print(err)
