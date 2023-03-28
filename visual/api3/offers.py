from flask import request, abort, current_app
from flask_login import current_user, login_required
from flask_babel import gettext

from . import mod, api_response
from visual.core import db
from visual.models import Offer, OfferChangedJurisdiction


def expand_fields(fields_param):
    fields = set(fields_param.split(','))
    if 'default' in fields:
        fields.remove('default')
        fields.update(['id', 'created', 'created_by', 'user_id', 'folder_id', 'type', 'hidden', 'title_ru', 'title_en',
                       'title_de', 'title_fr', 'template', 'template_data', 'cnt_tours', 'logo', 'tours'])

    return fields


def offer_api_repr(offer, fields):
    offer_properties = {'id', 'created', 'created_by', 'user_id', 'folder_id', 'type', 'hidden', 'title_ru', 'title_en',
                       'title_de', 'title_fr', 'template', 'template_data', 'cnt_tours'}
    res = {}
    warnings = []
    for field in fields:
        if field in offer_properties:
            val = getattr(offer, field)
        elif field in ('logo', ):
            val = getattr(offer, field).url
        elif field == 'tours':
            val = [{'tour_id': tour.tour_id, 'sort':tour.sort, 'title':tour.title} for tour in offer.tours]
        else:
            val = None
            warnings.append(gettext('Unknown field %(field)s', field=field))

        if val is not None:
            res[field] = val

    return res, warnings


@mod.route('/offers/<int:offer_id>')
def get_offer(offer_id):
    """GET /offers/<offer_id>
    Получить свойства одного мультитура.
    GET-параметры:
        ?fields: какие поля включить в ответ, через запятую, без пробелов. По умолчанию отдаются Offer.('id', 'created',
        'created_by', 'user_id', 'folder_id', 'type', 'hidden', 'title_ru', 'title_en', 'title_de', 'title_fr',
        'template', 'template_data', 'logo', 'cnt_tours', 'tours')
    Ответ:
        Offer
    """
    offer = Offer.query.get_or_404(offer_id)
    if not (current_user.is_authenticated and current_user.has_role('tours')):
        # Чужие офферы даём смотреть, только если он не hidden
        if not current_user.is_authenticated or current_user.id != offer.user_id:
            if offer.hidden:
                abort(403, 'You can not view this multitour.')

    fields = expand_fields(request.args.get('fields', 'default'))

    result, warnings = offer_api_repr(offer, fields)

    return api_response(result, warnings=warnings)


@mod.route('/offers/<int:offer_id>', methods=('DELETE', ))
@login_required
def delete_offer(offer_id):
    """DELETE /offers/<offer_id>
    Удалить мультитур.
    """
    offer = Offer.query.get_or_404(offer_id)
    if offer.user_id != current_user.id and not current_user.has_role('tours'):
        abort(403, 'You can not delete this multitour.')

    for offer_tour in offer.tours:
        db.session.delete(offer_tour)

    db.session.delete(offer)
    db.session.commit()

    return '', 204


@mod.route('/offers/changed_jurisdiction', methods=('POST', ))
@login_required
def offer_changed_jurisdiction():
    """POST /offers/changed_jurisdiction
    Внести данные в модель OfferChangedJurisdiction о перенесенном мультитуре.
    """
    if len({'local_id', 'remote_id', 'moved_to'} & set(request.json)) != 3:
        abort(400, 'You should specify local_id, remote_id, moved_to in input data.')

    remote_id = request.json.get('remote_id')
    moved_to = request.json.get('moved_to')

    offer = Offer.query.get_or_404(request.json['local_id'])
    if offer.user_id != current_user.id and not current_user.has_role('tours'):
        abort(403, 'You can not edit this multitour.')

    if offer and remote_id and moved_to in current_app.config.get('JURISDICTIONS_HOSTS').keys():
        offer_changed = OfferChangedJurisdiction(
            local_id=offer.id,
            remote_id=remote_id,
            moved_to=moved_to
        )

        db.session.add(offer_changed)
        db.session.flush()
        db.session.commit()
    else:
        abort(400, 'Bad data in input data.')

    return api_response({
        'local_id': offer_changed.local_id,
        'remote_id': offer_changed.remote_id,
        'moved_to': offer_changed.moved_to
    })
