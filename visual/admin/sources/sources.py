import os
import io
import fnmatch
import datetime
import zipfile

from flask import render_template, request, current_app, send_file
from flask_login import current_user

from .. import mod, roles_required


PLAYER_SOURCE_ROOT = 'visual/static/public/player/js-dev/custom'


def get_js_files():
    js_files = []

    for root, dir, files in os.walk(PLAYER_SOURCE_ROOT):
        for item in sorted(fnmatch.filter(files, "*.js"), key=str.lower):
            js_files.append(os.path.join(root, item))

    return js_files


@mod.route('/sources/player/')
@roles_required('sources.print')
def sources_player():    
    js_files = get_js_files()

    with open(current_app.config['ADMIN_SOURCES_LOGFILE'], 'a') as logfile:
        dnow = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logfile.write("player \t"+dnow+"\t "+request.remote_addr+"\t "+current_user.name+"\n")
    
    return render_template('admin/sources_player.html', files=js_files)


@mod.route('/sources/player/download/')
@roles_required('sources.print')
def sources_player_download():
    tmp = io.BytesIO()
    archive = zipfile.ZipFile(tmp, mode='w')

    for file_path in get_js_files():
        archive.write(file_path, arcname=file_path)

    archive.close()
    tmp.seek(0)

    return send_file(tmp, mimetype='application/zip', as_attachment=True, download_name='biganto-player.zip')


@mod.context_processor
def utility_processor():
    def print_src(file_path):
        lines = [i for i in open(file_path) if i[:-1]]
        sources = ''.join(lines)
        return sources
    return dict(print_src=print_src)
