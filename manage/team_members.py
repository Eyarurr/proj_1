from visual.models import User, TeamMember
from visual.core import db


class TeamMemberCreate:
    """Создаёт юзера и члена команды. Если юзер с такой почтой уже есть, то он становится членом команды.
    Вместо пароля можно указать "-", тогда юзер создастся без оного (то есть, войти им будет нельзя).
    """
    def run(self, roles, email, password):
        user = User.query.filter(db.func.lower(User.email) == email.lower()).first()
        if user is None:
            user = User(
                email=email,
                name=email.upper(),
                email_confirmed=True,
                admin_comment='Создано при помощи ./py.py team-member-create'
            )
            if password != '-':
                user.password_hash = User.hash_password(password)
            db.session.add(user)
            db.session.flush()
            print('Создан новый пользователь {}'.format(email))
        else:
            if user.team_member:
                print('У юзера {} уже есть членство в команде'.format(email))
                return
            print('Пользователь {} есть в базе, членом команды не является'.format(email))

        roles = roles.split(',')

        member = TeamMember(
            user_id=user.id,
            roles=roles,
            position=''
        )
        db.session.add(member)
        db.session.commit()

        print('Добавлено членство в команде с ролями {}'.format(roles))
