from collections import OrderedDict
import json
from datetime import datetime

from flask import render_template, abort, request, flash, redirect, url_for, jsonify, current_app, Response, g
from flask_login import current_user
from flask_babel import gettext
from sqlalchemy.orm.attributes import flag_modified

from . import mod
from ..models import User, Tour, Offer, Footage, AggregateCount, Folder
from ..core import db


@mod.route('/statistics/')
@mod.route('/statistics/<stat_type>/')
def statistics(stat_type='traffic'):
    """
    Статистика по туру или по нескольким турам
    Ввиду того, что пользователь может запрашивать статистику сразу по нескольким турам и объектам,
    будем вносить их идентификаторы в url посредством get-параметров
    """

    estates_id = []
    for id in request.args.get('estates_id', '').split(','):
        try:
            estates_id.append(int(id))
        except ValueError:
            pass
    tours_id = []
    for id in request.args.get('tours_id', '').split(','):
        try:
            tours_id.append(int(id))
        except ValueError:
            pass

    estates = {}
    data = db.session.query(Estate, Tour).join(Tour, Tour.estate_id == Estate.id). \
        join(Footage, Footage.id == Tour.footage_id).\
        filter(Estate.user_id == current_user.id, Footage.status == 'published', Estate.status == 'complete'). \
        group_by(Estate, Tour).all()
    for estate, tour in data:
        if estate.id not in estates:
            estates[estate.id] = {'estate': {'estate': estate, 'active': estate.id in estates_id}, 'tours': []}
        estates[estate.id]['tours'].append({'tour': tour, 'active': tour.id in tours_id})

    if stat_type not in ['traffic', 'geo', 'time', 'sources', None]:
        abort(404)

    return render_template('my/statistic.html',
                           estates_id=estates_id,
                           tours_id=tours_id,
                           estates=list(estates.values()),
                           stat_type=stat_type,
                           timezones=current_app.config['TIMEZONES'])
