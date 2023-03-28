import datetime

from visual.models import User, AuthToken
from visual.core import db


class CreateAuthToken:
    """Создаёт безо всякого пароля авторизационный токен для пользователя."""
    def run(self, email, expires, title):
        user = User.query.filter(db.func.lower(User.email) == email.lower()).first()
        if user is None:
            print('Пользователь {} не найден.'.format(email))
            return

        if expires:
            expires = datetime.datetime.fromisoformat(expires)
            if expires < datetime.datetime.now():
                print('Непонятный формат значения --expires. Юзайте ISO: "2022-08-08T16:20:00"')
        else:
            expires = datetime.datetime.now() + datetime.timedelta(days=30)

        if title is None:
            title = 'create-auth-token manage command.'
        token = AuthToken(ip='0.0.0.0', user_id=user.id, expires=expires, signature=AuthToken.generate(), title=title)
        db.session.add(token)
        db.session.commit()

        print(str(token))
