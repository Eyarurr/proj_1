import datetime

from flask import render_template, redirect, url_for, request
from flask_login import current_user
from flask import flash

from urllib.parse import urlparse

from visual.core import db
from visual.models import Link

from .. import mod


@mod.context_processor
def utility_processor():
    def baseN(num,b,numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
        return ((num == 0) and numerals[0]) or (baseN(num // b, b, numerals).lstrip(numerals[0]) + numerals[num % b])
    
    return dict(baseN=baseN)
    
@mod.route('/links/')
def links():
    links = Link.query.order_by(Link.created.desc(), Link.cnt_clicked.desc())
    pagination = links.paginate(per_page=50, error_out=False)

    return render_template('admin/links/index.html', links=pagination)


@mod.route('/links/new/', methods=['GET', 'POST'])
@mod.route('/links/<int:link_id>/edit/', methods=('GET', 'POST'))
def links_edit(link_id=None):
    if link_id:
        link = Link.query.options(db.joinedload(Link.author)).get_or_404(link_id)
    else:
        link = Link(created_by=current_user.id)
    
    if request.form.get('url'):
        parsed = urlparse(request.form.get('url'))
        if not (parsed.scheme and parsed.netloc):
            flash("Неверное значение url!", 'danger')
            return render_template('admin/links/edit.html', link=link)
            
        link.url=request.form.get('url')        
        db.session.add(link)
        db.session.commit()
        return redirect(url_for('.links', page = request.args.get('page')))

    return render_template('admin/links/edit.html', link=link)


@mod.route('/links/<link_id>/delete/', methods=('POST',))
def links_delete(link_id):
    link = Link.query.get_or_404(link_id)

    db.session.delete(link)
    db.session.commit()

    return redirect(url_for('.links'))
