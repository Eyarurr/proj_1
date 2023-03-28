from visual.core import db, storage


class Folder(db.Model):
    """
    Объект недвижимости. Принадлежит пользователю, содержит в себе 3D-туры, фотографии, презентации.
    """
    __tablename__ = 'folders'

    id = db.Column(db.Integer(), primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=db.text('now()'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(255))

    def api_view(self, **kwargs):
        return {
            **{
                'id': self.id,
                'created': self.created,
                'title': self.title
            },
            **kwargs
        }
