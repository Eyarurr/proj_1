from datetime import datetime

from flask import render_template, request, redirect, flash, url_for, jsonify, abort, current_app
from flask_login import current_user
from flask_babel import gettext

from visual.mail import send_email

from . import mod
from ..models import Issue
from ..core import db


@mod.route('/', methods=('GET', 'POST'))
def index():

    if request.method == 'POST':

        subject = request.json.get('subject')
        tour_link = request.json.get('tour', '').strip()
        issue = request.json.get('desc', '').strip()
        contact_email = request.json.get('email', '').strip()

        # валидация формы
        if subject not in ('tour', 'payment', 'feedback', 'other'):
            return jsonify({'errors': [gettext("Invalid subject.")]})
        if subject == 'tour' and tour_link == '':
            return jsonify({'errors': [gettext("Invalid tour link.")]})
        if issue == '':
            return jsonify({'errors': [gettext("Describe your issue.")]})
        if contact_email == '':
            return jsonify({'errors': [gettext("Invalid contact email.")]})

        # создание нового тикета
        first_issue = Issue.query.order_by(Issue.id.desc()).first()
        number = subject[0].upper() + datetime.now().strftime("%m%d") + str(getattr(first_issue, 'id', 0) + 1)

        issue = Issue(
            status='new',
            number=number,
            subject=subject,
            text=issue,
            contact_email=contact_email
        )
        if subject == 'tour':
            setattr(issue, 'tour_link', tour_link)
        if current_user.is_authenticated:
            issue.user_id = current_user.id

        db.session.add(issue)
        db.session.commit()

        # письмо на почтовый ящик техподдержки
        subject_email = 'Virtoaster support request #{}: {}. [{}]'.format(number, Issue.SUBJECTS.get(subject, subject),
                                                                          contact_email)
        send_email(
            subject_email,
            [current_app.config['SUPPORT_EMAIL']],
            template='admin/support/email/new_issue_created',
            issue=issue,
            user_id=issue.user_id
        )

        # письмо на почтовый ящик клиента
        subject_email = gettext('Virtoaster support request #%(number)s', number=number)
        if contact_email:
            send_email(
                subject_email,
                [contact_email],
                sender=current_app.config['SUPPORT_EMAIL'],
                template='front/email/new_issue_created',
                issue=issue
            )

        return jsonify({'status': 'ok'})

    return render_template('support/index.html')
