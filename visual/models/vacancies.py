from visual.core import db


class Vacancy(db.Model):

    __tablename__ = 'vacancies'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False, default='', server_default='')
    about = db.Column(db.Text(), nullable=False, default='', server_default='')    
    text = db.Column(db.Text(), nullable=False, default='', server_default='')    
    lang = db.Column(db.String(2), default='en', server_default='en', nullable=False, index=True)
    salary = db.Column(db.String(255))
    hidden = db.Column(db.Boolean, nullable=False, default=False, server_default='f')
    sort = db.Column(db.SmallInteger, nullable=False, default=0, server_default='0')
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)

