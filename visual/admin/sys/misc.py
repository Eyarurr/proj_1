import os

from flask import render_template, request, flash, redirect, url_for
from flask_login import current_user

from .. import mod, roles_required
from visual.mail import send_email
from visual.models import SoftwareVersion
from visual.core import db


@mod.route('/sys/testmail/', methods=('GET', 'POST'))
def sys_testmail():
    if request.method == 'POST':
        send_email(request.form['subject'], [request.form['to']], request.form['from'], html_body=request.form['body'], text_body=request.form['body'])
        flash('Сообщение ушло на {}'.format(request.form['to']), 'success')

    return render_template('admin/sys/testmail.html')


@mod.route('/sys/software/')
def sys_software():
    app_id = request.args.get('app_id')
    if app_id:
        versions = SoftwareVersion.query.filter_by(app_id=app_id).order_by(SoftwareVersion.version.desc()).all()
    else:
        versions = []

    return render_template('admin/sys/software.html', app_id=app_id, versions=versions)


@mod.route('/sys/software/upload/', methods=('POST', ))
def sys_software_upload():
    back = url_for('.sys_software', app_id=request.args.get('app_id'))

    sw = SoftwareVersion(app_id=request.args.get('app_id'), created_by=current_user.id)

    try:
        version = [int(x) for x in request.form.get('version').split('.', 2)]
        if len(version) != 3:
            raise ValueError
    except ValueError:
        flash('Версия приложения должна быть в формате X.Y.Z (Например "7.11.1917")', 'danger')
        return redirect(back)
    sw.version = version

    if request.form.get('type') == 'url':
        sw.download_url = request.form.get('download_url')
    elif request.form.get('type') == 'file':
        db.session.add(sw)
        db.session.flush()
        sw.file = request.files['file']
        sw.filename = request.files['file'].filename
        sw.filesize = os.stat(sw.file.abs_path).st_size

    db.session.add(sw)
    db.session.commit()

    return redirect(back)


@mod.route('/sys/software/delete', methods=('POST', ))
def sys_software_delete():
    back = url_for('.sys_software', app_id=request.args.get('app_id'))

    sw = SoftwareVersion.query.get_or_404(request.form.get('version_id'))
    if sw.file:
        del sw.file
    db.session.delete(sw)
    db.session.commit()

    return redirect(back)

    return(str(request.form))
