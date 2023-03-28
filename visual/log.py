import logging
import pprint
import sqlparse
import re
import ast
import datetime
from functools import partial
import colors


class FlaskFormatter(logging.Formatter):
    format_string = ('%(levelname)s ' + colors.black('%(asctime)s %(pathname)s:%(lineno)d\n') +
                     '%(message)s\n')

    def format(self, record):
        level_color = {
            'DEBUG': partial(colors.cyan, style='bold'),
            'INFO': partial(colors.white, style='bold+faint'),
            'WARNING': partial(colors.yellow, style='bold'),
            'ERROR': partial(colors.red, style='bold'),
            'CRITICAL': partial(colors.yellow, bg='red', style='bold')
        }
        record.levelname = level_color[record.levelname](record.levelname)
        record.message = record.getMessage()
        record.asctime = datetime.datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        return self.format_string % record.__dict__


class AlchemyFormatter(FlaskFormatter):
    def format(self, record):
        record.asctime = self.formatTime(record)
        _message = record.msg % record.args if record.args else record.msg
        record.args = None
        if _message[:1] == '{':
            params = ast.literal_eval(_message)
            record.msg = '\033[34m{}\033[0m'.format(pprint.pformat(params, indent=4))
        else:
            keywords = (
                'SELECT', 'FROM', 'LEFT', 'RIGHT', 'INNER', 'UNION', 'ALL', 'JOIN', 'GROUP', 'BY',
                'HAVING', 'INSERT', 'UPDATE', 'DELETE', 'VALUES', 'COMMIT', 'ROLLBACK',
                'LIMIT', 'OFFSET', 'WHERE', 'OUTER', 'CAST', 'ORDER', ' AS ', ' ON '
            )
            rep = {re.escape(k): '\033[1;32m{}\033[0;32m'.format(k) for k in keywords}
            pattern = re.compile('|'.join(rep.keys()))
            _message = pattern.sub(lambda m: rep[re.escape(m.group(0))],
                                   sqlparse.format(_message, reindent=True, keyword_case='upper'))
            record.msg = '\033[32m{}\033[0m'.format(_message)
        return super().format(record)


def init_logging(app):
    console_handler = logging.StreamHandler()

    if app.config['DEBUG']:
        console_handler.setLevel(logging.DEBUG)
    else:
        console_handler.setLevel(logging.ERROR)

    formatter = FlaskFormatter()
    console_handler.setFormatter(formatter)

    app.logger.handlers = []
    app.logger.propagate = False
    app.logger.addHandler(console_handler)

    db_logger_level = logging.INFO if app.config.get('SQLALCHEMY_TRUE_ECHO', False) else logging.WARNING

    db_formatter = AlchemyFormatter()

    db_handler = logging.StreamHandler()
    db_handler.setFormatter(db_formatter)

    db_logger = logging.getLogger('sqlalchemy.engine')
    db_logger.propagate = False

    db_logger.addHandler(db_handler)
    logging.getLogger('sqlalchemy.engine').setLevel(db_logger_level)