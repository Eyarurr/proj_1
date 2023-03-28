# Тестирует и профилирует bin/calc_passways, сравнивая граф достижимости, записаный в туре с вычисленным при помощи
# Footage.calc_passways().
#
# Запускается с аргументами:
# 666: проверить только на 666 съёмке
# 300-303: проверить на съёмках 300-303
# -300: проверить на съёмках с ID <= 300
# без аргументов: прогнать на всех
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import time
import argparse
from visual import create_app
from visual.models import Footage


app = create_app('config.local.py')


with app.app_context():
    parser = argparse.ArgumentParser()
    parser.add_argument('ids', type=str, default='all', nargs='?', help='ID съёмок: all|N|N-M, default=all')
    args = parser.parse_args()
    print(args.ids)

    total_time = 0
    cnt_footages = 0
    cnt_errors = 0

    q = Footage.query.filter_by(type='virtual').filter_by(_status='published').order_by(Footage.id.desc())
    if args.ids != 'all':
        if args.ids[0] == '-':
            q = q.filter(Footage.id <= int(args.ids[1:]))
        elif '-' in args.ids:
            a, b = args.ids.split('-')
            q = q.filter(Footage.id >= int(a), Footage.id <= int(b))
        else:
            q = q.filter(Footage.id == args.ids)
    else:
        print('ALL')

    for footage in q.all():
        if 'model' not in footage.meta:
            print('{}:  NO MODEL IN META'.format(footage.id), flush=True)
            continue

        start = time.time()
        try:
            new_pw = footage.calc_passways()
        except Exception as e:
            print('{}: EXCEPTION {}'.format(footage.id, e), flush=True)
            cnt_errors += 1
            continue
        dur = time.time() - start
        total_time += dur
        cnt_footages += 1

        if 'passways' not in footage.meta:
            print('{}: {:.3f} no passways in meta'.format(footage.id, dur, len(only_in_new) + len(only_in_old)), flush=True)
            continue

        # Сравниваем существующий passways с полученным
        new_pw = sorted([tuple(sorted(_)) for _ in new_pw])
        old_pw = sorted([tuple(sorted(_)) for _ in footage.meta['passways']])
        if old_pw != new_pw:
            cnt_errors += 1
            only_in_old, only_in_new = [], []
            for way in new_pw:
                if way not in old_pw:
                    only_in_new.append(way)
            for way in old_pw:
                if way not in new_pw:
                    only_in_old.append(way)
            print('{}: {:.3f} sec {} DIFF'.format(footage.id, dur, len(only_in_new) + len(only_in_old)), flush=True)
            print('    1.0: {}'.format(only_in_old), flush=True)
            print('    2.0: {}'.format(only_in_new), flush=True)
        else:
            print('{}: {:.3f} OK'.format(footage.id, dur), flush=True)

    print('{} footages, {:.3f} sec/tour, {} errors ({:.4f} rate)'.format(cnt_footages, total_time / cnt_footages, cnt_errors, cnt_errors/cnt_footages), flush=True)
