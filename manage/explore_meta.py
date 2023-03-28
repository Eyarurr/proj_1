import colors
from collections import Counter

from visual.models import Tour, Footage


class ExploreMeta:
    """Исследует мету туров и съёмок."""
    def run(self, **options):
        # key: {cnt: int, vals: set, patients: set}
        self.eprops = {}

        if options['what'] == 'tours':
            Patients = Tour
            q = Tour.query.outerjoin(Footage)
        else:
            Patients = Footage
            q = Patients.query

        if options['ids'] == 'all':
            pass
        elif ',' in options['ids']:
            q = q.filter(Patients.id.in_(options['ids'].split(',')))
        elif '-' in options['ids']:
            q = q.filter(Patients.id.between(*sorted([int(_) for _ in options['ids'].split('-')])))
        else:
            q = q.filter(Patients.id == int(options['ids']))

        if options['types'] is not None:
            q = q.filter(Footage.type.in_(options['types'].split(',')))

        if options['statuses'] is not None:
            q = q.filter(Footage._status.in_(options['statuses'].split(',')))

        q = q.order_by(Patients.created.desc())

        if options['limit'] is not None:
            q = q.limit(options['limit'])

        for patient in q.all():
            if options['property'] and (options['property'].endswith('.*') or options['property'].endswith('[]')):
                property = options['property'][:-2]
            else:
                property = options['property']

            if property and property not in patient.meta:
                continue

            if options['property'] and options['property'].endswith('.*'):
                for item_id, item in patient.meta[property].items():
                    self.explore(item, patient)
            elif options['property'] and options['property'].endswith('[]'):
                for item in patient.meta[property]:
                    self.explore(item, patient)
            elif options['property']:
                self.explore(patient.meta[options['property']], patient)
            else:
                self.explore(patient.meta, patient)

        print(' Тип   Свойство             |     N | Туры                                           | Значения')
        for prop, stat in sorted(self.eprops.items(), key=lambda x: x[1]['cnt'], reverse=True):
            ptype, pname = prop.split(' ')
            ptype = '{:5s}'.format(ptype)
            if len(pname) > 20:
                pname = pname[0:17] + '...'
            else:
                pname = '{:20s}'.format(pname)

            patients = ', '.join((str(_) for _ in stat['patients']))[0:40]

            if options.get('values'):
                print(' {} {} | {:5d} | {:4d}: {:40s}'.format(colors.blue(ptype), colors.bold(pname), stat['cnt'], len(stat['patients']), patients))
                print('       VALUES:')
                for val, cnt in stat['vals'].most_common():
                    print('       {}: {!r}'.format(cnt, val))
                print()
            else:
                vals_len = len(stat['vals'])
                if vals_len > 9:
                    vals_len = '9+'
                else:
                    vals_len = '{:2d}'.format(vals_len)
                vals_list = ', '.join(list(stat['vals'].keys())[:10]).replace('\n', '').replace('\r', '')[0:60]
                vals = '{}: {}'.format(vals_len, vals_list)

                print(' {} {} | {:5d} | {:4d}: {:40s} | {}'.format(colors.blue(ptype), colors.bold(pname), stat['cnt'], len(stat['patients']), patients, vals))

    def explore(self, data, patient):
        for k, v in sorted(data.items()):
            prop_name = ' '.join((type(v).__name__, k))
            self.eprops.setdefault(prop_name, {'cnt': 0, 'patients': set(), 'vals': Counter()})
            self.eprops[prop_name]['cnt'] += 1
            self.eprops[prop_name]['patients'].add(patient.id)
            self.eprops[prop_name]['vals'][str(v)] += 1
