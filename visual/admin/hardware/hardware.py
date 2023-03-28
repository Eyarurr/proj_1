import datetime

from sqlalchemy import or_

from flask import render_template, request, redirect, url_for, flash, render_template_string, jsonify
from flask_login import current_user
from sqlalchemy.sql.expression import func

from .. import mod
from ...core import db
from ...models import Hardware, User, TeamMember, Department, HardwareEvent
from .forms import AddHardwareForm, SortHardwareForm
from PIL import Image, UnidentifiedImageError

def add_event_for_hardware(gadget):
    """Добавляет событие"""
    event = HardwareEvent(user_id=gadget.user_id, hardware_id=gadget.id, location=gadget.location)
    db.session.add(event)
    db.session.commit()


@mod.route('/hardware/', methods=['POST', 'GET'])
@mod.route('/hardware/storage/<int:storage_id>', methods=['POST', 'GET'])
def hardware(storage_id=None):
    """ """
    add_form = AddHardwareForm()
    search_form = SortHardwareForm(request.args)
    search_form.user_id.choices = [(0, '')] + [(g.id, g.name) for g in
                                               User.query.join(TeamMember).order_by(User.name.asc())]
    departments = Department.query.all()
    add_form.user_id.choices = [(0, '')] + [(g.id, g.name) for g in User.query.join(TeamMember)]
    add_form.type.choices = [(key, val) for key, val in dict(Hardware.HARDWARE_TYPES).items()]
    add_form.location.choices = [(key, val) for key, val in dict(Hardware.HARDWARE_LOCATIONS).items()]
    if request.method == 'GET':
        query = db.session.query(Hardware, func.max(HardwareEvent.key_date)).join(HardwareEvent).group_by(Hardware.id)
        # вывод по отделам
        if storage_id:
            if storage_id != 100:
                query = query.join(TeamMember, Hardware.user_id == TeamMember.user_id).filter(
                    TeamMember.department_id == storage_id)
            else:
                query = query.filter(Hardware.user_id == None)

        # Поиск по имени, название. Описанию
        user = search_form.user_id.data
        if user:
            query = query.filter(Hardware.user_id == user)

        # Поиск по имени, название. Описанию
        search_ = search_form.search_.data
        if search_:
            query = query.outerjoin(User).filter(or_
                                                 (User.name.ilike(f'%{search_}%'),
                                                  Hardware.title.ilike(f'%{search_}%'),
                                                  Hardware.description.ilike(f'%{search_}%'),
                                                  Hardware.sn.ilike(f'%{search_}%')
                                                  )
                                                 )
        # Сортировка
        sorted_ = search_form.sorted_.data
        if sorted_:
            if sorted_ == 'buy_date':
                query = query.order_by(Hardware.buy_date.desc().nullslast())
            if sorted_ == 'title':
                query = query.order_by(Hardware.title.asc())
            if sorted_ == 'key_date':
                query = query.order_by(
                    func.max(HardwareEvent.key_date).desc())
            if sorted_ == 'type_hw':
                # сортируем словарь HARDWARE_TYPES
                pattern_sort = dict(sorted(Hardware.HARDWARE_TYPES.items(), key=lambda x: x[1]))
                pattern_sort = list(map(str, (pattern_sort).keys()))
                pattern_query = f"array_position(ARRAY{pattern_sort}::hardware_type[], type)"
                query = query.order_by(db.text(pattern_query))

        gadgets = query.paginate(per_page=50, error_out=False)
        return render_template('admin/hardware/index.html', gadgets=gadgets, form=add_form,
                               departments=departments, storage_id=storage_id, search_form=search_form
                               )

    if request.method == 'POST':
        if current_user.has_role('hardware.edit'):
            gadget = Hardware()
            add_form.populate_obj(gadget)
            if gadget.user_id == 0:
                gadget.user_id = None
                gadget.location = 'storage'
            db.session.add(gadget)
            db.session.flush()
            if add_form.img.data:
                gadget.photo = add_form.img.data
                gadget.preview = add_form.img.data
            add_event_for_hardware(gadget)
            db.session.commit()
        else:
            flash('Добавлять номенклатуру может только супер юзер', 'danger')
        return redirect(url_for('.hardware', add_gadgets='add_gadgets'))


@mod.route('/hardware/<int:gadget_id>/card')
def hardware_card(gadget_id):
    gadget = Hardware.query.get_or_404(gadget_id)
    history = HardwareEvent.query.filter(HardwareEvent.hardware_id == gadget.id).order_by(
        HardwareEvent.key_date.asc()).all()
    return render_template('admin/hardware/card.html', gadget=gadget, history=history)


@mod.route('/hardware/<int:gadget_id>/edit', methods=['POST', 'GET'])
@mod.route('/hardware/add_gadget', methods=['POST', 'GET'])
def hardware_edit(gadget_id=None):
    width = 800
    height = 600
    # Редактирование железки
    if gadget_id:
        gadget = Hardware.query.get_or_404(gadget_id)
        gadget_as_dict = gadget.view_api()
        initial_value = gadget.view_api()
        history = HardwareEvent.query.filter(HardwareEvent.hardware_id == gadget.id).order_by(
            HardwareEvent.key_date.desc()).all()
        edit_form = AddHardwareForm(obj=gadget)
        edit_form.user_id.choices = [(0, '')] + [(g.id, g.name) for g in
                                                   User.query.join(TeamMember).order_by(User.name.asc())]
        edit_form.type.choices = [(key, val) for key, val in dict(Hardware.HARDWARE_TYPES).items()]
        edit_form.location.choices = [(key, val) for key, val in dict(Hardware.HARDWARE_LOCATIONS).items()]
        if request.method == 'POST':
            if edit_form.validate_on_submit():
                if current_user.has_role('hardware.edit'):
                    edit_form.populate_obj(gadget)
                    if gadget.user_id == 0:
                        gadget.user_id = None
                        gadget.location = 'storage'
                    if gadget.location == 'storage':
                        if not gadget_as_dict['user_id'] and gadget.user_id:
                            flash(f'Указано неверное местоположение {gadget.get_location()}', 'danger')
                        gadget.user_id = None
                    db.session.add(gadget)
                    db.session.flush()
                    if edit_form.img.data:
                        try:
                            im = Image.open(edit_form.img.data)
                        except UnidentifiedImageError as e:
                            flash(f'Файл не является изображением', 'danger')
                            return redirect(url_for('.hardware_edit', gadget_id=gadget.id))
                        # загружаемое
                        width_im = im.size[0]
                        height_im = im.size[1]
                        if width >= width_im or height >= height_im:
                            flash(
                                f'Попытка добавить изображение размерами {width_im, height_im}. Изображение должно быть не менее (800,600)',
                                'danger')
                            return redirect(url_for('.hardware_edit', gadget_id=gadget.id))
                        gadget.photo = edit_form.img.data
                        gadget.preview = edit_form.img.data
                    # Добавим в историю, если проходит смена локации или юзера
                    if gadget.user_id != None and gadget.location == 'storage' or (
                            gadget.user_id == None and gadget.location != 'storage'):
                        flash(f'Указано неверное местоположение {gadget.get_location()}', 'danger')
                        return redirect(url_for('.hardware_edit', gadget_id=gadget.id))

                    if gadget.user_id == None and initial_value['user_id'] != None:
                        flash('Железка отправлена на склад, сотрудник сброшен', 'info')

                    if initial_value['location'] != gadget.location or initial_value['user_id'] != gadget.user_id:
                        add_event_for_hardware(gadget)
                    db.session.commit()
                    # Выводим, если были внесены изменения

                    if initial_value != gadget.view_api():
                        flash('Гаджет изменен', 'success')

                    if gadget.user and gadget.user.team_member.fired:
                        flash('Вы передали гаджет уволенному сотруднику. Вы отдаете себе в этом отчет?', 'danger')
                else:
                    flash('Нет необходимых привилегий', 'danger')
            else:
                flash('Проверьте правильность заполнения полей формы', 'danger')
            return redirect(url_for('.hardware_edit', gadget_id=gadget.id))

        return render_template('admin/hardware/edit.html', gadget=gadget, form=edit_form, history=history)

    # Добавление новых
    else:
        add_form = AddHardwareForm()
        add_form.user_id.choices = [(0, '')] + [(g.id, g.name) for g in
                                                  User.query.join(TeamMember).filter(TeamMember.fired == None).order_by(
                                                      User.name.asc())]
        add_form.type.choices = [(key, val) for key, val in dict(Hardware.HARDWARE_TYPES).items()]
        add_form.location.choices = [(key, val) for key, val in dict(Hardware.HARDWARE_LOCATIONS).items()]
        if request.method == 'POST':
            if current_user.has_role('hardware.edit'):
                if add_form.validate_on_submit():
                    gadget = Hardware()
                    add_form.populate_obj(gadget)
                    if gadget.user_id == 0:
                        gadget.user_id = None
                        gadget.location = 'storage'
                    db.session.add(gadget)
                    db.session.flush()
                    if add_form.img.data:
                        try:
                            im = Image.open(add_form.img.data)
                        except UnidentifiedImageError as e:
                            flash(f'Файл не является изображением', 'danger')
                            return redirect(url_for('.hardware_edit'))
                        width_im = im.size[0]
                        height_im = im.size[1]
                        if width >= width_im or height >= height_im:
                            flash(
                                f'Не подходящий размер изображения. Гаджет добавлен без изображения.', 'info')
                            add_event_for_hardware(gadget)
                            db.session.commit()
                            return redirect(url_for('.hardware_edit', gadget_id=gadget.id))
                        gadget.photo = add_form.img.data
                        gadget.preview = add_form.img.data
                    add_event_for_hardware(gadget)
                    db.session.commit()
                    flash(f'Гаджет {gadget.title} успешно добавлен', 'success')
                    return redirect(url_for('.hardware_edit'))
                else:
                    flash('Проверьте правильность заполнения полей формы', 'danger')
            else:
                flash('Добавлять номенклатуру может только  юзер hardware.edit', 'danger')

        return render_template('admin/hardware/edit.html', form=add_form)


@mod.route('/hardware/<int:gadget_id>/delete')
def hardware_delete(gadget_id):
    if current_user.has_role('super'):
        gadget = Hardware.query.get_or_404(gadget_id)
        try:
            db.session.delete(gadget)
            db.session.commit()
        except Exception as e:
            flash(f'Железка {gadget.title} не удалена.', 'danger')
        else:
            flash(f'Железка {gadget.title} удалена безвозвратно.', 'success')
    else:
        flash('Удалять номенклатуру может только супер юзер', 'danger')
    return redirect(url_for('.hardware'))


@mod.route('/hardware/<int:gadget_id>/to_take', methods=('GET', 'POST'))
def hardware_to_take(gadget_id):
    gadget = Hardware.query.get_or_404(gadget_id)
    gadget_as_dict = gadget.view_api()
    if request.method == 'POST':
        location = request.form.get('location')
        if gadget.user_id and gadget.user_id != current_user.id and location == 'storage':
            flash('Для чужой железки можно указать: домой взял или себе на стол', 'danger')
            return redirect(url_for('.hardware'))

        if gadget.user_id == None and location == 'storage':
            flash('Для складской железки можно указать: домой взял или на стол', 'danger')
            return redirect(url_for('.hardware'))
        if gadget_as_dict['user_id'] == current_user.id and location == 'storage':
            flash('Железка отправлена на склад, сотрудник сброшен', 'info')

        gadget.user_id = current_user.id
        if location == 'storage':
            gadget.user_id = None
        gadget.location = location
        if gadget_as_dict['location'] != gadget.location or gadget_as_dict['user_id'] != gadget.user_id:
            add_event_for_hardware(gadget)
            db.session.commit()


        return redirect(url_for('.hardware'))
    return jsonify(gadget.view_api())
