from visual.core import db


class MailingList(db.Model):
    __tablename__ = 'mailing_lists'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    title = db.Column(db.String(255))
    system = db.Column(db.Boolean, server_default=db.text('false'), default=False)


class MailingMessage(db.Model):
    __tablename__ = 'mailing_messages'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    mailing_list_id = db.Column(db.Integer, db.ForeignKey('mailing_lists.id'))
    subject = db.Column(db.String(255), nullable=False)
    content_html = db.Column(db.Text)
    content_text = db.Column(db.Text)
    status = db.Column(db.Enum('new', 'scheduled', 'sending', 'sent', name='mail_message_status'), default='new',
                       server_default='new')
    sending_started = db.Column(db.DateTime(timezone=True), nullable=True)
    sending_finished = db.Column(db.DateTime(timezone=True), nullable=True)
    sent_count = db.Column(db.Integer, nullable=True)

    @property
    def read_only(self):
        return self.status != 'new'

    @property
    def can_reset(self):
        return self.status == 'scheduled'

    @property
    def can_schedule(self):
        return self.status == 'new'

    def reset(self):
        if self.can_reset():
            self.sending_started = None
            self.sending_finished = None
            self.status = 'new'
            db.session.commit()
