import datetime
import gzip
import math
import os

from flask import render_template, request, current_app, render_template_string
from visual.core import db
from visual.models import TourBuilderStat as TBS
from visual.jobs.tour_inside_builder import Nizpodoh

from sqlalchemy.sql.expression import cast
from sqlalchemy import Float

from .. import mod, roles_required


@mod.route('/sys/builders/log/')
def builders_log():
    log = TBS.query\
        .order_by(TBS.started.desc())\
        .options(db.joinedload(TBS.footage))\
        .paginate(per_page=50, error_out=False)

    return render_template('admin/sys/builders/log.html', log=log)


@mod.route('/sys/builders/stat/')
def builders_stat():
    stat = {}
    start = datetime.datetime.now()

    def make_time(dt, func):
        return datetime.timedelta(seconds=func(dt or 0)).total_seconds() if dt else None

    def make_size(s):
        size = (s or 0) / (1024 ** 2)
        size = int(size) if size > 10 else round(size, 1)
        return size or ''

    def faces_time(t):
        return datetime.timedelta(seconds=float((t or 0) * 10 ** 6)).total_seconds() if t else None

    def faces_count(cnt):
        return round(int(cnt or 0) / 1000, 1) or ''

    builds_count = db.session.query(db.func.count(TBS.id)).scalar()
    builds_false = db.session.query(db.func.count(TBS.id)).filter(TBS.result == False).scalar()

    builds_time = db.session.\
        query(
            db.func.min(TBS.finished - TBS.started).label('time_min'),
            db.func.avg(TBS.finished - TBS.started).label('time_avg'),
            db.func.max(TBS.finished - TBS.started).label('time_max'),
        ).\
        filter(TBS.result == True).\
        first()

    highpoly_props = db.session.query(
            db.func.min(TBS.model_size_before).label('size_min'),
            db.func.avg(TBS.model_size_before).label('size_avg'),
            db.func.max(TBS.model_size_before).label('size_max'),
            db.func.min(TBS.model_objects_before).label('objects_min'),
            db.func.avg(TBS.model_objects_before).label('objects_avg'),
            db.func.max(TBS.model_objects_before).label('objects_max'),
            db.func.min(TBS.model_faces_before).label('faces_min'),
            db.func.avg(TBS.model_faces_before).label('faces_avg'),
            db.func.max(TBS.model_faces_before).label('faces_max')
        ).\
        filter(TBS.model_worker_actions.any('lowpoly')).\
        filter(TBS.result == True).\
        first()

    lowpoly_props = db.session.query(
            db.func.min(TBS.model_size_before).label('size_min'),
            db.func.avg(TBS.model_size_before).label('size_avg'),
            db.func.max(TBS.model_size_before).label('size_max'),
            db.func.min(TBS.model_objects_before).label('objects_min'),
            db.func.avg(TBS.model_objects_before).label('objects_avg'),
            db.func.max(TBS.model_objects_before).label('objects_max'),
            db.func.min(TBS.model_faces_before).label('faces_min'),
            db.func.avg(TBS.model_faces_before).label('faces_avg'),
            db.func.max(TBS.model_faces_before).label('faces_max')
        ).\
        filter(~(TBS.model_worker_actions.all('lowpoly'))).\
        filter(TBS.result == True).\
        first()

    model_out_props = db.session.query(
            db.func.min(TBS.model_size_after).label('size_min'),
            db.func.avg(TBS.model_size_after).label('size_avg'),
            db.func.max(TBS.model_size_after).label('size_max'),
            db.func.min(TBS.model_faces_after).label('faces_min'),
            db.func.avg(TBS.model_faces_after).label('faces_avg'),
            db.func.max(TBS.model_faces_after).label('faces_max')
        ). \
        filter(TBS.result == True). \
        first()

    objects_removed = db.session. \
        query(db.func.min(TBS.model_objects_before - TBS.model_objects_after).label('objects_min'),
              db.func.avg(TBS.model_objects_before - TBS.model_objects_after).label('objects_avg'),
              db.func.max(TBS.model_objects_before - TBS.model_objects_after).label('objects_max'),
              ). \
        filter(TBS.result == True).\
        first()

    model_worker_time = db.session. \
        query(
            db.func.avg(TBS.model_worker_time),
        ). \
        filter(TBS.result == True). \
        scalar()

    mesh_props_high = db.session.query(
            db.func.min(TBS.model_worker_meshtransform_time).label('time_min'),
            db.func.avg(TBS.model_worker_meshtransform_time).label('time_avg'),
            db.func.max(TBS.model_worker_meshtransform_time).label('time_max'),
            db.func.avg(TBS.model_size_before / TBS.model_size_after).label('model_size_ratio_avg'),
            db.func.avg(TBS.model_faces_before / TBS.model_faces_after).label('model_faces_ratio_avg'),
            db.func.avg(TBS.model_worker_meshtransform_time / TBS.model_objects_after).label('objects_time'),
            db.func.avg(cast(TBS.model_worker_meshtransform_time, Float) / TBS.model_faces_before).label('faces_time'),
        ). \
        filter(TBS.model_worker_actions.any('lowpoly')). \
        filter(TBS.result == True). \
        first()

    mesh_props_low = db.session.query(
            db.func.min(TBS.model_worker_meshtransform_time).label('time_min'),
            db.func.avg(TBS.model_worker_meshtransform_time).label('time_avg'),
            db.func.max(TBS.model_worker_meshtransform_time).label('time_max'),
            db.func.avg(TBS.model_size_before / TBS.model_size_after).label('model_size_ratio_avg'),
            db.func.avg(TBS.model_faces_before / TBS.model_faces_after).label('model_faces_ratio_avg'),
            db.func.avg(cast(TBS.model_worker_meshtransform_time, Float) / TBS.model_faces_before).label('faces_time'),
        ). \
        filter(~TBS.model_worker_actions.all('lowpoly')). \
        filter(TBS.result == True). \
        first()

    texturing = db.session.query(
            db.func.min(TBS.model_worker_texturing_time).label('time_min'),
            db.func.avg(TBS.model_worker_texturing_time).label('time_avg'),
            db.func.max(TBS.model_worker_texturing_time).label('time_max'),
            db.func.avg(cast(TBS.model_worker_texturing_time, Float) / TBS.cnt_skyboxes).label('time_point')
        ). \
        filter(TBS.model_worker_actions.any('dollhouse')). \
        filter(TBS.result == True). \
        first()

    cutter = db.session.query(
            db.func.min(TBS.wurst_cutter_time).label('time_min'),
            db.func.avg(TBS.wurst_cutter_time).label('time_avg'),
            db.func.max(TBS.wurst_cutter_time).label('time_max'),
            db.func.avg(cast(TBS.wurst_cutter_time, Float) / TBS.cnt_skyboxes).label('time_point')
        ). \
        filter(TBS.result == True). \
        first()

    cnt_errors = db.session. \
        query(
            db.func.count(TBS.id)
        ). \
        filter(TBS.result == False). \
        scalar()

    errors = db.session. \
        query(db.func.count(TBS.id).label('cnt'), TBS.model_worker_exit_code.label('code')). \
        group_by(TBS.model_worker_exit_code). \
        order_by(db.desc('cnt')). \
        filter(TBS.model_worker_exit_code != 0). \
        all()
    end = datetime.datetime.now()

    stat['builds_count'] = builds_count
    stat['builds_false'] = builds_false
    stat['builds_false_percentage'] = '{:.0%}'.format(builds_false/(builds_count or 1))
    stat['builds_time'] = {}
    stat['builds_time']['min'] = make_time(builds_time.time_min.seconds if builds_time.time_min else 0 , int)
    stat['builds_time']['avg'] = make_time(builds_time.time_avg.seconds if builds_time.time_avg else 0, int)
    stat['builds_time']['max'] = make_time(builds_time.time_max.seconds if builds_time.time_max else 0, int)
    stat['highpoly_props'] = {}

    stat['highpoly_props']['size_min'] = make_size(highpoly_props.size_min)
    stat['highpoly_props']['size_avg'] = make_size(highpoly_props.size_avg)
    stat['highpoly_props']['size_max'] = make_size(highpoly_props.size_max)
    stat['highpoly_props']['objects_min'] = highpoly_props.objects_min or ''
    stat['highpoly_props']['objects_avg'] = int(highpoly_props.objects_avg or 0) or ''
    stat['highpoly_props']['objects_max'] = highpoly_props.objects_max or ''
    stat['highpoly_props']['faces_min'] = faces_count(highpoly_props.faces_min)
    stat['highpoly_props']['faces_avg'] = faces_count(highpoly_props.faces_avg)
    stat['highpoly_props']['faces_max'] = faces_count(highpoly_props.faces_max)

    stat['lowpoly_props'] = {}
    stat['lowpoly_props']['size_min'] = make_size(lowpoly_props.size_min)
    stat['lowpoly_props']['size_avg'] = make_size(lowpoly_props.size_avg)
    stat['lowpoly_props']['size_max'] = make_size(lowpoly_props.size_max)
    stat['lowpoly_props']['objects_min'] = lowpoly_props.objects_min or ''
    stat['lowpoly_props']['objects_avg'] = int(lowpoly_props.objects_avg or 0) or ''
    stat['lowpoly_props']['objects_max'] = lowpoly_props.objects_max or ''
    stat['lowpoly_props']['faces_min'] = faces_count(lowpoly_props.faces_min)
    stat['lowpoly_props']['faces_avg'] = faces_count(lowpoly_props.faces_avg)
    stat['lowpoly_props']['faces_max'] = faces_count(lowpoly_props.faces_max)

    stat['model_out_props'] = {}
    stat['model_out_props']['size_min'] = make_size(model_out_props.size_min)
    stat['model_out_props']['size_avg'] = make_size(model_out_props.size_avg)
    stat['model_out_props']['size_max'] = make_size(model_out_props.size_max)
    stat['model_out_props']['faces_min'] = faces_count(model_out_props.faces_min)
    stat['model_out_props']['faces_avg'] = faces_count(model_out_props.faces_avg)
    stat['model_out_props']['faces_max'] = faces_count(model_out_props.faces_max)

    stat['objects_removed'] = {}
    stat['objects_removed']['objects_avg'] = int(objects_removed.objects_avg or 0) or ''

    stat['model_worker_time'] = make_time(model_worker_time, int)

    stat['mesh_props_high'] = {}
    stat['mesh_props_high']['time_min'] = make_time(mesh_props_high.time_min, int)
    stat['mesh_props_high']['time_avg'] = make_time(mesh_props_high.time_avg, int)
    stat['mesh_props_high']['time_max'] = make_time(mesh_props_high.time_max, int)
    stat['mesh_props_high']['model_size_ratio_avg'] = int(mesh_props_high.model_size_ratio_avg or 0) or ''
    stat['mesh_props_high']['model_faces_ratio_avg'] = int(mesh_props_high.model_faces_ratio_avg or 0) or ''
    stat['mesh_props_high']['objects_time'] = float(mesh_props_high.objects_time or 0) or None
    stat['mesh_props_high']['faces_time'] = faces_time(mesh_props_high.faces_time)

    stat['mesh_props_low'] = {}
    stat['mesh_props_low']['time_min'] = make_time(mesh_props_low.time_min, int)
    stat['mesh_props_low']['time_avg'] = make_time(mesh_props_low.time_avg, int)
    stat['mesh_props_low']['time_max'] = make_time(mesh_props_low.time_max, int)
    stat['mesh_props_low']['model_size_ratio_avg'] = int(mesh_props_low.model_size_ratio_avg or 0) or ''
    stat['mesh_props_low']['model_faces_ratio_avg'] = int(mesh_props_low.model_faces_ratio_avg or 0) or ''
    stat['mesh_props_low']['faces_time'] = faces_time(mesh_props_low.faces_time)

    stat['texturing'] = {}
    stat['texturing']['time_min'] = make_time(texturing.time_min, int)
    stat['texturing']['time_avg'] = make_time(texturing.time_avg, int)
    stat['texturing']['time_max'] = make_time(texturing.time_max, int)
    stat['texturing']['time_point'] = float(texturing.time_point or 0) or None

    stat['cutter'] = {}
    stat['cutter']['time_min'] = make_time(cutter.time_min, int)
    stat['cutter']['time_avg'] = make_time(cutter.time_avg, int)
    stat['cutter']['time_max'] = make_time(cutter.time_max, int)
    stat['cutter']['time_point'] = float(cutter.time_point or 0) or None

    stat['cnt_errors'] = cnt_errors
    stat['cnt_errors_percentage'] = '{:.0%}'.format(cnt_errors / (builds_count or 1))

    stat['errors'] = {}
    stat['gen_time'] = (end-start).seconds

    for error in errors:
        stat['errors'][error.code] = {
            'text': Nizpodoh.get_error_message(error.code),
            'N': error.cnt,
            'percentage': '{:.0%}'.format(error.cnt / (cnt_errors or 1))[:-1]
        }

    return render_template('admin/sys/builders/stat.html', stat=stat)


@mod.route('/sys/builders/logs_list/')
@mod.route('/sys/builders/logs_list/<logfile>')
def builders_logs_list(logfile=None):
    search = request.args.get('search')
    abs_path = os.path.abspath(current_app.config.get('BUILDER_LOGS_DIR'))
    logfiles = [item for item in os.listdir(abs_path) if 'builder.log' in item]

    page = request.args.get('page', 1, type=int)
    per_page = 50
    total_files = len(logfiles)

    # Поиск
    if search:
        logfiles = [item for item in logfiles if search in item]

    # Формируем список файлов
    if logfile is None:
        builders_logs = []
        for item in logfiles[per_page * (page - 1): per_page * (page - 1) + per_page]:
            date = datetime.datetime.fromtimestamp(os.path.getctime(os.path.join(abs_path, item))).strftime('%Y-%m-%d')
            log = dict(file=item,
                       date=date,
                       size=f'{os.path.getsize(os.path.join(abs_path, item)) / 1024:.2f} Кб'
                       )
            builders_logs.append(log)

        builders_logs = sorted(builders_logs, key=lambda k: k['date'])
        return render_template('admin/sys/builders/logs_list.html', builders_logs=builders_logs, cur_page=page,
                               total_files=total_files, per_page=per_page, count_page=math.ceil(total_files / per_page))
    else:
        if logfile.split('.')[-1] != 'gz':
            with open(os.path.join(abs_path, logfile), 'r') as f:
                log = f.read()
        else:
            with gzip.open(os.path.join(abs_path, logfile), 'rb') as f:
                log = f.read()
            log = log.decode('utf-8')

        return render_template('admin/sys/builders/logs_list.html', log=log, file=logfile)

