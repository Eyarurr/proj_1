import os
import time

from flask import render_template, request, redirect, url_for, flash
from sqlalchemy.orm.attributes import flag_modified

from visual.core import db
from visual.models import Tour
from .. import mod, roles_required
from ...util import unlink_calm


@mod.route('/tours/<int:tour_id>/branding/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/branding/', methods=('GET', 'POST'))
@roles_required('tours')
def tour_branding(tour_id, user_id=None):
    positions = ('top-left', 'top-center', 'top-right', 'left', 'center', 'right', 'bottom-left', 'bottom-center', 'bottom-right')

    tour = Tour.query.get_or_404(tour_id)

    if request.method == 'POST':
        branding = tour.meta.get('branding', {})
        copyrights = []
        for copyright in ['copyright_map_null', 'copyright_help_null']:
            key = copyright[:-5]
            if request.form.get(copyright):
                if key in branding:
                    del branding[key]
            else:
                copyrights.append(key)
        if len(copyrights):
            for k, v in request.form.items():
                for copyright in copyrights:
                    if copyright in k:
                        x = k.split('.')
                        if len(x) == 1:
                            branding[copyright] = v
                        elif len(x) == 2:
                            if copyright not in branding or type(branding[copyright]) is not dict:
                                branding[copyright] = {}
                            branding[copyright][x[1]] = v

        if not branding.get('watermark', None):
            branding['watermark'] = {}
        watermark = {'opacity': None, 'position': None}

        watermark_url = request.form.get('watermark_url', None)
        # Получаем как строку
        if watermark_url:
            if branding['watermark'].get('url', ''):
                unlink_calm(tour.in_files(branding['watermark'].get('url')))
            watermark['url'] = watermark_url

        file = request.files.get('watermark_url', None)
        if file and file.filename:
            url_type = file.filename[file.filename.rfind('.'):].lower()
            file_name = '{}{}'.format(str(time.time()), url_type)
            tour.mkdir()
            os.makedirs(tour.in_files('branding'), exist_ok=True)
            if branding['watermark'].get('url', ''):
                unlink_calm(tour.in_files(branding['watermark'].get('url')))

            watermark['url'] = 'branding/' + file_name
            file.save(tour.in_files(watermark['url']))

        if request.form.get('watermark_opacity', None):
            try:
                opacity_new = float(request.form.get('watermark_opacity'))
                if not 0 <= opacity_new <= 1:
                    raise ValueError
                watermark['opacity'] = opacity_new
            except ValueError:
                flash(f'Неверное значение для opacity', 'danger')
                return redirect(url_for('.tour_branding', tour_id=tour_id, user_id=user_id))

        if request.form.get('watermark_position', None):
            watermark['position'] = request.form.get('watermark_position')

        branding['watermark'].update(watermark)
        branding['watermark'] = {key: val for key, val in branding['watermark'].items() if val is not None}

        if request.form.get('watermark_delete', None):
            if branding['watermark'].get('url', ''):
                unlink_calm(tour.in_files(branding['watermark'].get('url')))
            del branding['watermark']

        if request.form.get('logo_help_type') == 'url':
            logo = request.files.get('logo_help')
            print('SET LOGO', logo, logo.filename)
            if logo and logo.filename:
                logo_type = logo.filename[logo.filename.rfind('.'):].lower()
                file_name = '{}{}'.format(str(time.time()), logo_type)

                tour.mkdir()
                os.makedirs(tour.in_files('branding'), exist_ok=True)
                try:
                    os.unlink(tour.in_files(branding.get('logo_help')))
                except(OSError, TypeError, AttributeError):
                    pass

                branding['logo_help'] = 'branding/' + file_name
                logo.save(tour.in_files(branding['logo_help']))
        elif request.form.get('logo_help_type') == 'empty':
            try:
                os.unlink(tour.in_files(branding.get('logo_help')))
            except (OSError, TypeError, AttributeError):
                pass
            branding['logo_help'] = ''
        else:
            try:
                os.unlink(tour.in_files(branding.get('logo_help')))
            except (OSError, TypeError, AttributeError):
                pass
            branding.pop('logo_help', None)

        branding['logo_help_link'] = request.form.get('logo_help_link', None)
        if not branding['logo_help_link']:
            del branding['logo_help_link']

        if branding:
            tour.meta['branding'] = branding
        elif 'branding' in tour.meta:
            del tour.meta['branding']

        # Blotch
        blotch_properties = ('blotch_text', 'blotch_html')
        blotch = {}
        for k, v in request.form.items():
            # Для i18n-свойств, проверяем ключи 'blotch_something' и 'blotch_something.anylangcode'
            x = k.split('.')
            if x[0] not in blotch_properties:
                continue
            v = v.strip()
            if v == '':
                continue
            prop = x[0][7:]
            if len(x) == 1:
                blotch[prop] = v
            else:
                blotch.setdefault(prop, {})
                blotch[prop][x[1]] = v
        if blotch:
            tour.meta['blotch'] = blotch
        else:
            tour.meta.pop('blotch', None)

        flag_modified(tour, 'meta')
        tour.save_features()
        db.session.commit()
        flash('Изменения сохранены, ура!', 'success')

        return redirect(url_for('.tour_branding', tour_id=tour_id, user_id=user_id))

    return render_template('admin/tours/branding.html', tour=tour, user_id=user_id, positions=positions)
