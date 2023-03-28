from flask import render_template, redirect, url_for, request

from visual.core import db
from visual.util import flash_errors
from visual.models import Partner

from .. import mod, roles_required

from .forms import PartnerForm, PartnerWithLogoForm


@mod.route('/partners/')
def partners(lang='ru'):
    partners = Partner.query.order_by(Partner.sort).all()

    return render_template('admin/partners/index.html', partners=partners)


@mod.route('/partners/new/', methods=['GET', 'POST'])
@mod.route('/partners/<int:partner_id>/edit/', methods=('GET', 'POST'))
@roles_required('texts')
def partners_edit(partner_id=None):
    if partner_id:
        partner = Partner.query.filter_by(id=partner_id).first_or_404()
        form = PartnerWithLogoForm(obj=partner)
    else:
        partner = Partner()
        partner.sort = (db.session.query(db.func.min(Partner.sort)).scalar() or 0) - 1
        form = PartnerForm(obj=partner)

    if form.validate_on_submit():
        db.session.add(partner)
        db.session.flush()

        form.populate_obj(partner)

        db.session.commit()

        return redirect(url_for('.partners'))
    else:
        flash_errors(form)

    return render_template('admin/partners/edit.html', partner=partner, form=form)


@mod.route('/partners/<int:partner_id>/delete/', methods=('POST',))
@roles_required('texts')
def partner_delete(partner_id):
    partner = Partner.query.get_or_404(partner_id)

    db.session.delete(partner)
    db.session.commit()

    return redirect(url_for('.partners'))


@mod.route('/partners/reorder/', methods=('POST',))
@roles_required('texts')
def partners_reorder():
    for k, v in request.form.items():
        if k.startswith('sort.'):
            Partner.query.filter_by(id=k[5:]).update({'sort': v})
    db.session.commit()

    return 'om-nom-nom!'
