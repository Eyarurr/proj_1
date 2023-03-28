from flask import render_template, request, redirect, flash, url_for, jsonify, abort, current_app, g
from flask_login import login_user, logout_user, login_required

from . import mod


@mod.route('/')
def index():
    return render_template('tutorials/index.html')


@mod.route('/how_it_works/')
def how_it_works():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/how_it_works.{}.html'.format(g.lang))


@mod.route('/system_requirements/')
def system_requirements():
    return render_template('tutorials/system_requirements.{}.{}.html'.format(current_app.config.get('JURISDICTION'), g.lang))


@mod.route('/quick_start_guide/')
def quick_start_guide():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/quick_start_guide.{}.html'.format(g.lang))


@mod.route('/setting_up_camera/')
def setting_up_camera():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/setting_up_camera.{}.html'.format(g.lang))


@mod.route('/preparing_geometry/')
def preparing_geometry():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/preparing_geometry.{}.html'.format(g.lang))


@mod.route('/setting_up_render/')
def setting_up_render():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/setting_up_render.{}.html'.format(g.lang))


@mod.route('/post_production/')
def post_production():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/post_production.{}.html'.format(g.lang))


@mod.route('/tour_editing_mode/')
def tour_editing_mode():
    return render_template('tutorials/tour_editing_mode.{}.html'.format(g.lang))


@mod.route('/uploading_assets/')
def uploading_assets():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/uploading_assets.{}.html'.format(g.lang))


@mod.route('/creating_interactive_objects/')
def creating_interactive_objects():
    return render_template('tutorials/creating_interactive_objects.{}.html'.format(g.lang))

@mod.route('/interactive_meshes/')
def interactive_meshes():
    return render_template('tutorials/interactive_meshes.{}.html'.format(g.lang))

@mod.route('/rendering_floor_plan/')
def rendering_floor_plan():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/rendering_floor_plan.{}.html'.format(g.lang))


@mod.route('/shades/')
def shades():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/shades.{}.html'.format(g.lang))


@mod.route('/releasing_tour/')
def releasing_tour():
    return render_template('tutorials/releasing_tour.{}.{}.html'.format(current_app.config.get('JURISDICTION'), g.lang))


@mod.route('/edit_assets/')
def edit_assets():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/edit_assets.{}.html'.format(g.lang))


@mod.route('/troubleshooting/')
def troubleshooting():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/troubleshooting.{}.html'.format(g.lang))


@mod.route('/installing_oculus/')
def installing_oculus():
    return render_template('tutorials/installing_oculus.{}.html'.format(g.lang))


@mod.route('/desktop_player/')
def desktop_player():
    return render_template('tutorials/desktop_player.{}.html'.format(g.lang))


@mod.route('/branding/')
def branding():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/branding.{}.html'.format(g.lang))


@mod.route('/model_replacement/')
def model_replacement():
    if current_app.config['JURISDICTION'] == 'ru':
        abort(404)
    return render_template('tutorials/model_replacement.{}.html'.format(g.lang))
