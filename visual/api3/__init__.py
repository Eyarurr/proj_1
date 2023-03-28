from flask import Blueprint, jsonify, request, g
from visual.core import csrf
from flask_babel import gettext

VERSION = '3.0'

mod = Blueprint('api3', __name__, url_prefix='/api/v3')
csrf.exempt(mod)


def api_response(result=None, warnings=None, bgjobs=None, pagination=None):
    resp = {'result': result}
    if warnings:
        resp['warnings'] = warnings
    if bgjobs:
        resp['bgjobs'] = bgjobs
    if pagination:
        resp['pagination'] = pagination
    return jsonify(resp)


@mod.before_request
def check_request():
    fails = []

    skip_endpoints = ('api3.download_devcon_tasks_file', )

    if request.endpoint and request.endpoint in skip_endpoints:
        return

    if 'client' not in request.args:
        fails.append(gettext('No client ID in request.'))
    else:
        g.api_client = request.args['client']

    if 'client_version' not in request.args:
        fails.append(gettext('No client version in request.'))
    else:
        g.api_client_version = request.args['client_version']

    if fails:
        return jsonify({'errors': fails}), 400


from . import users, folders, tours, footages, audio, skyboxes, floors, loading, billing, branding, shadows, gallery, navigator, misc, statistics, \
    overlays, actions, joint, offers, remote_processing, notifications, meshes, devcon, tour_videos, tags, estates,\
    domhub, bladerunner
