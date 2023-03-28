from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms import validators as v
from flask_babel import lazy_gettext


class SettingsForm(FlaskForm):
    password = StringField('Пароль', [v.optional()])


class RemindPasswordForm(FlaskForm):
    email = StringField('E-mail', [v.data_required(lazy_gettext("Please, enter your e-mail."))])


class RestorePasswordForm(FlaskForm):
    password = PasswordField('Пароль', [v.data_required(message=lazy_gettext("Enter password."))])
    password2 = PasswordField('Пароль ещё раз', [v.data_required(message=lazy_gettext("Confirm password"))])