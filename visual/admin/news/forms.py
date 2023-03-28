from flask_wtf import FlaskForm
from wtforms import TextAreaField
from wtforms import validators as v


def strip(t):
    if isinstance(t, str):
        return t.strip()
    return t


class NewsArticleForm(FlaskForm):
    message = TextAreaField('Новость', validators=[v.data_required('О чём новость-то?')], filters=[strip])
