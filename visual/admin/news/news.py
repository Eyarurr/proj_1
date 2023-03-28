import datetime

from flask import render_template, redirect, url_for, request
from flask_login import current_user
from sqlalchemy.orm.attributes import flag_modified

from visual.core import db
from visual.util import flash_errors
from visual.models import NewsArticle

from .. import mod

from .forms import NewsArticleForm


@mod.route('/news/')
def news():
    articles = NewsArticle.query.order_by(NewsArticle.created.desc()).all()

    if articles:
        current_user.settings_obj.news_last_seen = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        current_user.settings_save()
        db.session.commit()

    if request.args.get('mode') == 'feed':
        return render_template('admin/news/feed.html', articles=articles)
    else:
        return render_template('admin/news/index.html', articles=articles)


@mod.route('/news/new/', methods=['GET', 'POST'])
@mod.route('/news/<int:article_id>/edit/', methods=('GET', 'POST'))
def news_edit(article_id=None):
    if article_id:
        article = NewsArticle.query.get_or_404(article_id)
    else:
        article = NewsArticle(user_id=current_user.id)

    form = NewsArticleForm(obj=article)

    if form.validate_on_submit():
        form.populate_obj(article)
        db.session.add(article)
        db.session.commit()

        return redirect(url_for('.news'))
    else:
        flash_errors(form)

    return render_template('admin/news/edit.html', article=article, form=form)


@mod.route('/news/<article_id>/delete/', methods=('POST',))
def news_delete(article_id):
    article = NewsArticle.query.get_or_404(article_id)

    db.session.delete(article)
    db.session.commit()

    return redirect(url_for('.news'))
