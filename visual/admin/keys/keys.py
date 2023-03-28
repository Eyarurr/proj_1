from datetime import datetime

from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user
from sqlalchemy import desc, asc

from visual.core import db
from visual.models import SoftwareDistributionKey as SDK
from .. import mod


@mod.route('/keys/', methods=('GET', 'POST'))
def keys():
    app_id = request.args.get('app_id')
    active = request.args.get('active', 'active')

    if not app_id:
        app_id = 'goplayer'

    if active not in ('active', 'inactive'):
        active = 'active'

    q = SDK.query.filter(SDK.app_id == app_id).order_by(desc(SDK.created))

    active_keys = q.filter(SDK.used == None).paginate(per_page=10, error_out=False)
    inactive_keys = q.filter(SDK.used != None).paginate(per_page=10, error_out=False)

    applications = []
    for a_id, a in current_app.config['APPLICATIONS'].items():
        if a.get('uses_distr_keys'):
            applications.append(a_id)

    return render_template('admin/keys/index.html', app_id=app_id, active_keys=active_keys, inactive_keys=inactive_keys, applications=applications)


@mod.route('/keys/add/', methods=('GET', 'POST'))
def keys_add():
    app_id = request.args.get('app_id')
    keys = request.form.get('keys').split('\r\n')
    keys = list(map(str.strip, keys))
    dublicate_keys = []

    for key in keys:
        new_key = SDK(
            app_id=app_id,
            used_by=None,
            key=key
        )
        dublicate = SDK.query.filter(SDK.key==key, SDK.app_id==app_id).first()
        if dublicate:
            dublicate_keys.append(dublicate.key)
        else:
            db.session.add(new_key)
            db.session.flush()
    if dublicate_keys:
        flash('Ключи:<br> %s <br>не добавлены, так как дубликаты.' % '<br>'.join(dublicate_keys), 'warning')

    if len(dublicate_keys) == len(keys):
        flash('Ключи не добавлены.', 'warning')
        pass
    else:
        added_keys = list(set(dublicate_keys) ^ set(keys))
        flash('Ключи:<br> %s <br>успешно добавлены.' % '<br>'.join(added_keys), 'info')
        db.session.commit()

    return redirect(url_for('.keys', app_id=app_id))


@mod.route('/keys/edit/', methods=('GET', 'POST'))
def keys_edit():
    app_id = request.args.get('app_id')
    active = request.args.get('active')
    action = request.args.get('action')
    key_id = request.args.get('key_id')
    used = datetime.now() if action == 'deactivate' else None

    q = SDK.query.filter(app_id == app_id)

    if action in ('activate', 'deactivate'):
        q.filter(SDK.id == key_id).update({'used': used, 'used_by': None}, synchronize_session=False)
        db.session.commit()
        flash('Ключ успешно %s.' % ('деактивирован' if action == 'deactivate' else 'активирован'), 'info')
    elif action == 'delete':
        key = SDK.query.filter_by(id=key_id).first()

        db.session.delete(key)
        db.session.commit()
        flash('Ключ успешно удален.', 'info')

    return redirect(url_for('.keys', app_id=app_id, active=active))
