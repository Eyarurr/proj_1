from datetime import datetime, timedelta
from os import listdir, unlink
from os.path import isfile, splitext, basename, join, isdir

from visual.models import Footage


class CleanModels:
    """Чистка неиспользуемых моделей"""
    def run(self, before, after, dry=False):
        q = Footage.query.\
            filter(Footage.type.in_(['outside', 'virtual']), Footage.status.in_(['published', 'banned']))

        if before:
            q = q.filter(datetime.now() - Footage.created >= timedelta(days=before))
        if after:
            q = q.filter(datetime.now() - Footage.created <= timedelta(days=after))

        footages = q.order_by(Footage.id.desc()).all()

        for footage in footages:
            purgatory = []

            if {'models', 'model'} & set(footage.meta):
                models_path = footage.in_files('models')
                if not isdir(models_path):
                    continue

                models_inmeta = [basename(footage.meta['model'])] if 'model' in footage.meta else \
                    list(map(basename, list(footage.meta['models'].values())))

                models_list = [f for f in listdir(models_path) if isfile(join(models_path, f))
                               and splitext(f)[1].lower() == '.obj']
                diff = set(models_list) - set(models_inmeta)

                if diff:
                    for model_filename in list(diff):
                        purgatory.append(model_filename)

                    if purgatory:
                        print('Съемка #{}'.format(footage.id))
                        print('Удаляем модели: {}'.format(', '.join(purgatory)))

                        if not dry:
                            for model_filename in purgatory:
                                unlink(footage.in_files('models', model_filename))
