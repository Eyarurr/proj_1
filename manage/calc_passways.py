import traceback

from flask import current_app
from sqlalchemy.orm.attributes import flag_modified

from visual.models import Footage
from visual.core import db
from visual.bgjobs import BgJobState
from .progress import Progress


class CalcPassways:
    """Пересчитывает граф достижимости для указанных съёмок."""

    def _diff(self, old, new):
        """Возвращает разницу между двумя графами достижимости."""
        s1 = set(map(tuple, old))
        s2 = set(map(tuple, new))
        sX = s1 ^ s2
        return sorted(list(sX), key=lambda x: int(x[0]))

    def run(self, footage_id, no_recalc=None, compare=None, quiet=False):
        if quiet:
            self.bgstate = BgJobState('passways', footage_id, 'processing')
        else:
            self.bgstate = None
        self.progress = Progress(quiet=quiet, bgstate=self.bgstate)

        footage = Footage.query.get(footage_id)
        if not footage:
            self.progress.error('Съёмка id={} не найдена'.format(footage_id))
            return

        self.progress.say('Считаем граф достижимости для съёмки {}'.format(footage.id))

        self.work(footage, no_recalc, compare)

        self.progress.end()

    def work(self, footage, no_recalc, compare):
        if no_recalc and 'passways' in footage.meta:
            self.progress.say('Съёмка %d: passways уже есть.' % footage.id)
            return

        if compare and 'passways' not in footage.meta:
            self.progress.say('Съёмка %d: нет passways, пропускаем.' % footage.id)
            return

        try:
            result = footage.calc_passways()
        except Exception as e:
            self.progress.error('Съёмка %d: плохая, плохая модель %s: %s' % (footage.id, footage.meta['model'], e))
            current_app.logger.error(traceback.format_exc())
            return

        if compare:
            if 'passways' in footage.meta:
                diff = self._diff(footage.meta['passways'], result)
                if diff:
                    print(
                        'Съёмка %d: граф достижимости пересчитан, d(O)=%d, d(N)=%d, d(D)=%d d=%f'
                        % (footage.id, len(footage.meta['passways']), len(result), len(diff), len(diff) / len(footage.meta['passways']))
                    )
                else:
                    print('Съёмка %d: граф достижимости такой же' % footage.id)

        if not compare:
            # Читаем съёмку из базы ещё раз, на случай если она поменялась, пока считался граф
            footage = Footage.query.get(footage.id)
            footage.meta['passways'] = result
            flag_modified(footage, 'meta')
            db.session.commit()
