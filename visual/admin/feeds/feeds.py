import datetime
import pytz

from flask import render_template, redirect, url_for, request, flash, jsonify
from lagring import AssetProcessingException

from visual.core import db
from visual.models import NewsFeed, NewsFeedTranslation, NewsPhoto, NewsPhotoTranslation

from .. import mod


@mod.route('/feeds/')
def feeds():
    feeds_list = db.session.query(
            NewsFeed.id,
            NewsFeed.created,
            NewsFeed.hidden,
            NewsFeedTranslation.title,
            NewsFeedTranslation.announce,
        ).\
        join(NewsFeedTranslation, NewsFeedTranslation.feed_id == NewsFeed.id).\
        filter(NewsFeedTranslation.lang == 'en').\
        order_by(NewsFeed.created.desc()).\
        paginate(per_page=10, error_out=False)

    return render_template('admin/feeds/index.html', feeds_list=feeds_list)


@mod.route('/feeds/new/', methods=('GET', 'POST'))
@mod.route('/feeds/<int:feed_id>/edit/', methods=('GET', 'POST'))
def feeds_edit(feed_id=None, new_lang=None):
    lang = request.args.get('lang') or new_lang
    feed_translations = {}
    photos = {}
    photo_translations = {}

    if feed_id:
        feed_data = db.session.query(NewsFeed, NewsFeedTranslation).\
            join(NewsFeedTranslation, NewsFeedTranslation.feed_id == NewsFeed.id).\
            filter(NewsFeed.id == feed_id).\
            all()

        for feed, feed_translation in feed_data:
            feed_translations[feed_translation.lang] = feed_translation
    else:
        lang = 'en'
        feed = NewsFeed(created=datetime.datetime.now(tz=pytz.timezone('Etc/UTC')))
        # feed = NewsFeed(created=datetime.datetime.now())
        feed_translations[lang] = NewsFeedTranslation(title='', announce='', text='', published=True)

    if request.form:
        new_lang = request.values.get('new_lang', False)

        if new_lang or new_lang == '':
            if len(new_lang) == 0:
                flash('Не задан язык.', 'warning')
                return redirect(url_for('.feeds_edit', feed_id=feed_id, lang='en'))
            elif new_lang and new_lang in feed_translations:
                flash('Такой язык уже есть.', 'warning')
                return redirect(url_for('.feeds_edit', feed_id=feed_id, lang='en'))

            feed_translation = NewsFeedTranslation()
            feed_translation.feed_id = feed_id
            feed_translation.lang = new_lang
        else:
            feed.created = request.values.get('published')
            preview_image = request.files.get('image')
            if not preview_image or preview_image.filename == '':
                pass
            else:
                feed.original = preview_image
                feed.preview = preview_image

            feed_translation = feed_translations[lang]
            feed_translation.published = bool(request.values.get('hidden'))

            if lang == 'en':
                feed.hidden = not feed_translation.published

            feed_translation.title = request.values.get('title')
            feed_translation.announce = request.values.get('announce')
            feed_translation.text = request.values.get('body')

            db.session.add(feed)
            db.session.flush()
            feed_translation.feed_id = feed.id

            for photo_file in request.files.getlist('images'):
                if photo_file.filename != '':
                    photo = NewsPhoto(feed_id=feed.id)
                    db.session.add(photo)
                    db.session.flush()

                    try:
                        photo.image = photo_file
                        photo.preview = photo_file
                        photo.original = photo_file
                    except AssetProcessingException:
                        db.session.delete(photo)
                        flash('Не удалось обработать файл %s. Убедитесь, что он нормальный.' % photo_file.filename,
                              'danger')

        db.session.add(feed_translation)
        db.session.flush()
        db.session.commit()

        if not feed_id:
            new_lang = 'en'
            feed_id = feed.id
        if new_lang:
            return redirect(url_for('.feeds_edit', feed_id=feed_id, lang=new_lang))

    if feed_id:
        photos = NewsPhoto.query.filter_by(feed_id=feed_id).order_by(NewsPhoto.id.desc()).all()

        photos_data = db.session.query(NewsPhoto, NewsPhotoTranslation). \
            join(NewsPhotoTranslation, NewsPhotoTranslation.photo_id == NewsPhoto.id). \
            filter(NewsPhoto.feed_id == feed_id). \
            order_by(NewsPhoto.id.desc()). \
            all()

        for photo, photo_translation in photos_data:
            if photo.id not in photo_translations:
                photo_translations[photo.id] = {}
            photo_translations[photo.id].update({photo_translation.lang: photo_translation.title})

    return render_template('admin/feeds/edit.html', lang=lang, feed=feed, feed_translations=feed_translations,
                           photos=photos, photo_translations=photo_translations)


@mod.route('/feeds_translations/<int:feed_translation_id>/delete/', methods=('POST',))
def feed_translation_delete(feed_translation_id):
    feed_translation = db.session.query(NewsFeedTranslation).filter_by(id=feed_translation_id).first_or_404()
    feed_id = feed_translation.feed_id

    if feed_translation.lang == 'en':
        feed = NewsFeed.query.filter_by(id=feed_id).first_or_404()
        del feed.original
        del feed.preview
        db.session.delete(feed)
        flash('Новость удалена на всех языках.', 'success')
        db.session.commit()
        return redirect(url_for('.feeds'))
    else:
        db.session.delete(feed_translation)
        flash('Новость на выбранном языке удалена.', 'success')

        db.session.commit()
        return redirect(url_for('.feeds_edit', feed_id=feed_id, lang='en'))


@mod.route('/feeds/photo/<int:photo_id>/delete/', methods=('POST', ))
def feeds_photo_delete(photo_id=None):
    photo = db.session.query(NewsPhoto).get_or_404(photo_id)
    del photo.original
    del photo.preview
    del photo.image
    db.session.delete(photo)
    db.session.commit()
    return jsonify({'photo_id': photo_id})


@mod.route('/feeds/photo/<int:photo_id>/edit/', methods=('POST', ))
def feeds_photo_edit(photo_id=None):
    title = request.form.get('title', '')
    hidden = bool(request.values.get('hidden'))
    lang = request.form.get('lang')

    db.session.query(NewsPhoto). \
        filter(NewsPhoto.id == photo_id). \
        update({'hidden': hidden}, synchronize_session=False)

    photo_translation = NewsPhotoTranslation.query. \
        filter(NewsPhotoTranslation.photo_id == photo_id). \
        filter(NewsPhotoTranslation.lang == lang). \
        first()

    if photo_translation:
        db.session.query(NewsPhotoTranslation).\
            filter(NewsPhotoTranslation.photo_id == photo_id, NewsPhotoTranslation.lang == lang).\
            update({'title': title}, synchronize_session=False)
    else:
        photo_translation = NewsPhotoTranslation(title=title, lang=lang, photo_id=photo_id)
        db.session.add(photo_translation)

    db.session.commit()
    return jsonify({'id': photo_id, 'title': title, 'hidden': hidden})
