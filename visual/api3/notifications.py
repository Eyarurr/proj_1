"""
Нотификации
"""
from flask_babel import gettext
from flask_login import current_user, login_required
from flask import request, current_app, g, abort

from . import mod, api_response
from visual.models import Notification, User
from visual.core import db, upload_slots_service
from visual.mail import send_email


@mod.route('/my/notifications')
@login_required
def get_notifications():
    """Отдаёт список нотификаций текущего юзера, сортированный по дате создания.
    Помечает просмотренными все нотификации, созданные ранее самой первой нотификации в ответе.
    GET-параметры:
        ?offset, ?limit - offset и limit для запроса
    Ответ:
        [Notification, ...]
    """
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 30, type=int)

    if offset < 0:
        offset = 0
    if offset > 1000:
        offset = 1000
    if limit < 0:
        limit = 0
    if limit > 100:
        limit = 100

    result = []
    q = Notification.query.filter(Notification.user_id == current_user.id)\
        .order_by(Notification.created.desc()).offset(offset).limit(limit)

    youngest = None
    for notification in q.all():
        if youngest is None:
            youngest = notification.created
        result.append(notification.api_repr())

    # Помечаем просмотренными все нотификации, ранее самой первой
    if youngest:
        Notification.query\
            .filter(Notification.user_id == current_user.id, Notification.created <= youngest)\
            .update({'seen': db.func.now()})
        db.session.commit()

    return api_response(result)


@mod.route('/users/<int:user_id>/notifications', methods=('POST', ))
@mod.route('/my/notifications', methods=('POST', ))
@login_required
def user_notify(user_id=None):
    """
    Отправляет нотификацию юзеру. Тело запроса:
    {
        "channel": str,
        "tone": enum(Notification.TONES),
        "message": str,
        "link": str,
        "email_subject": str
        "email_html": html,
        "email_text": str
    :param user_id:
    :return:
    """
    if user_id is None:
        user = current_user
    else:
        user = User.query.get_or_404(user_id, description=gettext('User not found.'))

    if user.id != current_user.id:  # and not current_user.has_role('notify')
        abort(403, gettext('You have not enough rights to send notifications to this user.'))

    if 'channel' not in request.json:
        abort(400, gettext('You must specify channel in notification request.'))

    if request.json['channel'] not in Notification.CHANNELS:
        abort(400, gettext('Unrecognized channel "%(channel)s".', channel=request.json['channel']))

    if 'tone' not in request.json:
        abort(400, gettext('You must specify notification tone.'))

    if request.json['tone'] not in Notification.TONES:
        abort(400, gettext('Unrecognized notification tone "%(tone)s".', tone=request.json['tone']))

    if 'message' not in request.json or type(request.json['message']) is not str or request.json['message'] == '':
        abort(400, gettext('Malformed %(key)s value.', key='message'))

    if 'link' not in request.json or type(request.json['link']) is not str or request.json['link'] == '':
        abort(400, gettext('Malformed %(key)s value.', key='link'))

    if 'email_subject' in request.json:
        if type(request.json['email_subject']) is not str or request.json['email_subject'] == '':
            abort(400, gettext('Malformed %(key)s value.', key='email_subject'))
        email_subject = request.json['email_subject'][:200]

        email_html = request.json.get('email_html')
        email_text = request.json.get('email_text')
        if not email_html and not email_text:
            abort(400, gettext('No email body in notification request.'))

    else:
        email_subject = None
        email_html = None
        email_text = None

    notification = user.notify(
        channel=request.json['channel'],
        tone=request.json['tone'],
        message=request.json['message'],
        link=request.json['link'],
        email_subject=email_subject,
        email_html=email_html,
        email_text=email_text,
    )

    return api_response(notification.api_repr())


@mod.route('/my/notifications/count')
@login_required
def get_notifications_count():
    """
    Возвращает количество непрочитанных нотификаций
    {
        "unseen": int
    }
    """

    return api_response({'unseen': current_user.notifications_unseen()})
