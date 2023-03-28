import os
import shutil
import datetime

from flask import render_template, request, flash, send_file, redirect, url_for, abort

from visual.core import db
from visual.models import Footage, Tour
from visual.admin import mod
from flask.views import View


class FileManger(View):
    methods = ['GET', 'POST']

    def __init__(self, template_name, entity):
        self.template_name = template_name
        self.entity = entity

    def get_content(self, dir_name, rel_path):
        """Формирует словарь со списком вложенных папок и файлов """
        content = {}
        folders = []
        files = []
        abs_path = os.path.join(dir_name, rel_path)
        content_directory = os.listdir(abs_path)

        for file in content_directory:
            abs_path_file = os.path.join(abs_path, file)
            if os.path.isdir(abs_path_file):
                folders.append(file)
            else:
                files.append(
                    {'name': file, 'created': datetime.datetime.fromtimestamp(os.path.getctime(abs_path_file)),
                     # 'size': f'{(os.path.getsize(abs_path_file)) / 1024:.2f} Кб'})
                     'size': (os.path.getsize(abs_path_file))})

        content['folders'] = sorted(folders, key=lambda k: k.lower())
        content['files'] = sorted(files, key=lambda k: k['name'])
        return content

    def create_directories(self, object):
        """Создает директорию Тура/съемки, если не существует"""
        if not object.files.abs_path:
            object.mkdir()
            db.session.add(object)
            db.session.commit()

    def add_folder(self, object, rel_path, new_folder):
        """Добавляет каталог"""
        abs_path = os.path.join(object.files.abs_path, rel_path)
        try:
            os.mkdir(os.path.join(abs_path, new_folder))
            flash(f'Каталог {new_folder} добавлен', 'success')
        except Exception as e:
            flash(f'Каталог существует или не указан.', 'danger')

    def add_files(self, object, rel_path, files, overwrite):
        """Добавит файлы в текущую дирректорию"""
        for file in files:
            abs_path = os.path.join(object.files.abs_path, rel_path, file.filename)
            if os.path.isdir(abs_path):
                flash(f'Не выбраны файлы для добавления', 'danger')
            elif os.path.exists(abs_path):
                if not overwrite:
                    flash(f'Файл {file.filename} уже существует', 'danger')
                else:
                    file.save(abs_path)
                    flash(f' {file.filename} перезаписан', 'success')
            else:
                file.save(abs_path)
                flash(f' {file.filename} сохранен в текущей папке', 'success')

    def del_files(self, object, rel_path, name):
        """ Удаляет директорию или файл в текущей директории"""
        abs_path = os.path.join(object.files.abs_path, rel_path, name)
        if os.path.isdir(abs_path):
            # удаляем директорию
            try:
                shutil.rmtree(abs_path)
                flash(f'Успешно удален каталог {name}', 'success')
            except Exception as e:
                flash(f'Удалить каталог не удалось, обратитесь к админам', 'danger')
        else:
            # удаляем файл
            try:
                os.remove(abs_path)
                flash(f'Файл {name} удален', 'success')
            except Exception as e:
                flash(f'Файл {name} не удален', 'danger')

    def form_render_templates(self, context):
        return render_template(self.template_name, **context)

    def dispatch_request(self, obj_id):
        if request.method == 'GET':
            if self.entity == 'footage':
                self.object = db.session.query(Footage).get_or_404(obj_id)
            if self.entity == 'tour':
                self.object = db.session.query(Tour).get_or_404(obj_id)

            rel_path = request.args.get('rel_path', '')
            what = request.args.get('what', None)
            if not what:
                self.create_directories(self.object)
                if not os.path.abspath(os.path.join(self.object.files.abs_path, rel_path)).startswith(
                        self.object.files.abs_path):
                    return abort(404)
                content = self.get_content(self.object.files.abs_path, rel_path)
                context = {f'{self.entity}': self.object, 'content': content, 'rel_path': rel_path,
                           'entity': self.entity, 'user_id': self.object.user_id}
                return self.form_render_templates(context)
            elif what == 'download':
                name = request.args.get('name', '')
                abs_path = os.path.join(self.object.files.abs_path, rel_path, name)
                return send_file(abs_path, as_attachment=True)

        if request.method == 'POST':
            if self.entity == 'footage':
                self.object = db.session.query(Footage).get_or_404(obj_id)
                self.endpoint = 'admin.footage_files'
            if self.entity == 'tour':
                self.object = db.session.query(Tour).get_or_404(obj_id)
                self.endpoint = 'admin.tour_files'
            rel_path = request.args.get('rel_path', '')
            what = request.args.get('what', None)

            if what == 'add_folder':
                new_folder = request.form.get('folder', '')
                self.add_folder(self.object, rel_path, new_folder)
            if what == 'add_files':
                files = request.files.getlist('files')
                overwrite = request.form.get('overwrite')
                self.add_files(self.object, rel_path, files, overwrite)
            if what == 'del':
                name = request.args.get('name', '')
                if not os.path.abspath(os.path.join(self.object.files.abs_path, rel_path)).startswith(
                        self.object.files.abs_path):
                    return abort(404)
                self.del_files(self.object, rel_path, name)

            return redirect(url_for(self.endpoint, obj_id=self.object.id, rel_path=rel_path))


# endpoint для footage
mod.add_url_rule('/footage/<int:obj_id>/files/', view_func=FileManger.as_view(
    'footage_files', template_name='/admin/files_manager/files_manager.html', entity='footage'))
# endpoint для tours about.html
mod.add_url_rule('/tour/<int:obj_id>/files/', view_func=FileManger.as_view(
    'tour_files', template_name='/admin/files_manager/files_manager.html', entity='tour'))
