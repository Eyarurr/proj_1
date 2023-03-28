"""
Правка меты: html убирается из свойств вида str, str_i18n
"""
import sys
import os
import re

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from visual import create_app
from visual.core import db
from visual.models import Footage, Tour

from sqlalchemy.orm.attributes import flag_modified

app = create_app('config.local.py')

def sanitize(str):
    tags = {
        '<br>': '\n',
        '<sup>2</sup>': '²',
        '&sup2;': '²'
    }

    for tag in tags:
        str = str.replace(tag, tags[tag])
    str = re.sub('(<[^>]+>)', '', str)
    return str


with app.app_context():
    keys = [
        'toolbar',
        'navigator',
        'audio',
        'active_meshes',
        'splash',
        'blotch',
        'overlays',
        'skyboxes',
        'actions'
    ]


    for tour in Tour.query.\
            join(Footage, Tour.footage_id == Footage.id).\
            filter(Footage.type.in_(['virtual'])).all():

        meta = tour.meta

        for meta_key in keys:
            if meta_key == 'actions':
                for key, action in meta.get(meta_key, {}).items():
                    if 'name' in action and '<' in action['name']:
                        action['name'] = sanitize(action['name'])
                    if 'title' in action and '<' in action['title']:
                        action['title'] = sanitize(action['title'])
                    if 'buttons' in action:
                        for button in action['buttons']:
                            if 'text' in button and '<' in button['text']:
                                button['text'] = sanitize(button['text'])
            if meta_key == 'skyboxes':
                for key, skybox in meta.get(meta_key, {}).items():
                    if 'title' in skybox and ('<' in skybox['title'] or 'sup' in skybox['title']):
                        skybox['title'] = sanitize(skybox['title'])
                    if 'audio' in skybox:
                        for key, audio_clip in skybox['audio'].items():
                            if 'title' in audio_clip and '<' in audio_clip['title']:
                                audio_clip['title'] = sanitize(audio_clip['title'])
            if meta_key == 'overlays':
                for key, overlay in meta.get(meta_key, {}).items():
                    if 'tooltip' in overlay and '<' in overlay['tooltip']:
                        overlay['tooltip'] = sanitize(overlay['tooltip'])
                    if 'widget' in overlay and 'text' in overlay['widget']:
                        if '<' in overlay['widget']['text']:
                            overlay['widget']['text'] = sanitize(overlay['widget']['text'])
            if meta_key == 'blotch':
                if meta_key in meta and 'text' in meta[meta_key]:
                    if '<' in meta[meta_key]['text']:
                        meta[meta_key]['text'] = sanitize(meta[meta_key]['text'])
            if meta_key == 'splash':
                if meta_key in meta and 'cancel_text' in meta[meta_key]:
                    if '<' in meta[meta_key]['cancel_text']:
                        meta[meta_key]['cancel_text'] = sanitize(meta[meta_key]['cancel_text'])
            if meta_key == 'active_meshes':
                for key, active_mesh in meta.get(meta_key, {}).items():
                    if 'title' in active_mesh and '<' in active_mesh['title']:
                        active_mesh['title'] = sanitize(active_mesh['title'])
            if meta_key == 'audio':
                for key, audio_clip in meta.get(meta_key, {}).items():
                    if 'title' in audio_clip and '<' in audio_clip['title']:
                        audio_clip['title'] = sanitize(audio_clip['title'])
            if meta_key == 'navigator':
                for navigator_element in meta.get(meta_key, []):
                    if 'title' in navigator_element and '<' in navigator_element['title']:
                        navigator_element['title'] = sanitize(navigator_element['title'])
            if meta_key == 'toolbar':
                for toolbar_element in meta.get(meta_key, []):
                    if 'title' in toolbar_element and '<' in toolbar_element['title']:
                        toolbar_element['title'] = sanitize(toolbar_element['title'])
                    if 'text' in toolbar_element and '<' in toolbar_element['text']:
                        toolbar_element['text'] = sanitize(toolbar_element['text'])

        flag_modified(tour, 'meta')
    db.session.commit()




