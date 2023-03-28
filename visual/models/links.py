from visual.core import db


class Link(db.Model):
    """
    Ссылки
    """
    __tablename__ = 'links'

    id = db.Column(db.Integer(), primary_key=True)    
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    created_by = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'))
    url = db.Column(db.Text(), nullable=False)
    cnt_clicked = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    
    author = db.relationship('User')
