from flask import render_template, request, url_for, flash, jsonify, current_app
from flask_babel import gettext
from sqlalchemy import desc

from visual.core import db
from visual.mail import send_email
from visual.models import Issue
from .. import mod


@mod.route('/support/')
def issues():
    count_issues = {}
    for status, n in db.session.query(Issue.status, db.func.count('*')).group_by(Issue.status).all():
        count_issues[status] = n

    issues = Issue.query.order_by(desc(Issue.created))\
                  .filter_by(status=request.args.get('status', 'new'))\
                  .paginate(per_page=20, error_out=False)
    return render_template('admin/support/index.html', issues=issues, count_issues=count_issues, Issue=Issue, statuses=Issue.STATUSES)


@mod.route('/support/<int:issue_id>/edit/', methods=('GET', 'POST'))
def issue_edit(issue_id):
    issue = Issue.query.get_or_404(issue_id)

    if request.method == 'POST':

        if request.json:
            # смена статуса тикета
            new_status = request.json.get('status')
            if new_status:
                prev_status = issue.status
                if new_status not in ['new', 'process', 'complete', 'spam']:
                    flash('Нельзя установить заказу статус «{}»'
                          .format(Issue.STATUSES.get(new_status, new_status)), 'danger')
                    return jsonify({'redirect': url_for('.issues', status=prev_status)})
                issue.status = new_status
                flash('Тикету {} установлен статус «{}»'
                      .format(issue.number, Issue.STATUSES.get(new_status, new_status)), 'success')

            db.session.commit()

            if new_status in ['complete', 'spam']:
                return jsonify({'reload': True})
            return jsonify({'redirect': url_for('.issue_edit', issue_id=issue.id)})

        else:
            # ответ на тикет
            if request.form.get('message'):
                subject_email = gettext('Virtoaster support request #%(number)s', number=issue.number)
                send_email(
                    subject_email,
                    [issue.contact_email],
                    sender=current_app.config['SUPPORT_EMAIL'],
                    template='front/email/issue_answer',
                    message=request.form.get('message'),
                )
                flash('Сообщение отправлено на почтовый ящик {}.'.format(issue.contact_email), 'success')
            else:
                flash('Сообщение не может быть пустым.', 'danger')

    return render_template('admin/support/edit.html', issue=issue, Issue=Issue)
