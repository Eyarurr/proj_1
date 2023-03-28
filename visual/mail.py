import os
import smtplib
import re
import uuid

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.charset import Charset
from email.utils import formataddr

from flask import current_app, render_template


def get_extension(path):
    s = path.rsplit('.', 1)
    if len(s) == 1:
        # no extension
        return ''
    else:
        return '.' + s[-1]


def extract_statics(html):
    """
    Ищем в теле html картинки, и если src ссылается на static, выдираем ресурс в виде абсолютного
    пути к файлу, а тег img модифицируем, чтобы он ссылался на аттачмент
    Возвращаем модифицированный html и словарь с картинками вида:
    {
        'image0': <путь>,
        ...
    }
    """
    images = {}
    srcs_found = set()

    # теги img
    # весь тег кладётся в именованную группу img, src в группу src
    re_static_img = re.compile("(?P<img><img\s+[^>]*?src\s*=\s*['\"](?P<src>/static/[^'\"]*?)['\"][^>]*?>)")

    for m in re_static_img.finditer(html):
        src = m.groupdict()['src']
        if src not in srcs_found:
            srcs_found.add(src)
            cid = 'image_{}'.format(uuid.uuid4().hex)
            images[cid] = {
                'orig_path': src,
                'abs_path': os.path.join(current_app.root_path, src[1:]),
            }

    for cid, v in images.items():
        html = html.replace(v['orig_path'], 'cid:{}'.format(cid))

    return html, {k: v['abs_path'] for k, v in images.items()}


def attach_images(msgRoot, images):
    """
    Аттачит картинки к письму

    msgRoot - MIMEMultipart, куда присобачиваются вложения
    images - словарь вида: 
        {
            '<имя>': <путь>|<file-like object>,
            ....
        }
    """
    for name, path in images.items():
        if not hasattr(path, 'read'):
            f = open(path, 'rb')
        else:
            f = path

        msgImage = MIMEImage(f.read())
        msgImage.add_header('Content-ID', '<{}>'.format(name))
        msgImage.add_header('Content-Disposition', 'attachment; filename={}{}'.format(
                                str(name), get_extension(path)))
        msgRoot.attach(msgImage)

        f.close()


def contact(address):
    if isinstance(address, tuple):
        return formataddr((Charset('utf-8').header_encode(address[0]), address[1]))
    else:
        return address


def contact_list(address_list):
    return ', '.join((contact(address) for address in address_list))


def address(contact):
    return contact[1] if isinstance(contact, tuple) else contact


def send_email(subject, recipients, sender=None, attach=None,
               html_body=None, text_body=None, template=None, ignore_smtp_errors=True, **kwargs):
    """
    Отправка самосборного письма.
    Ссылки на картинке в статике превращаются в аттачменты. Текст правильно кодируется, чтобы
    избежать багов с переносом строки в Flask-Mail

    recipients - Список
    attach - Вложения, словарь имя-путь
    template - Имя шаблона без расширения. Будет искаться пара файлов <template>.html и <template>.txt

    """
    cfg = current_app.config

    if sender is None:
        sender = cfg.get('MAIL_DEFAULT_SENDER', 'no-reply@{}'.format(cfg.get('SERVER_NAME', 'example.com')))

    if template:
        html_body, text_body = render_email(template, **kwargs)

    if cfg.get('MAIL_SINK'):
        recipients = cfg.get('MAIL_SINK')

    recipients_str = contact_list(recipients)

    charset = Charset(input_charset='utf-8')

    msgRoot = MIMEMultipart('related')
    msgRoot['Subject'] = charset.header_encode(subject)
    msgRoot['From'] = contact(sender)
    msgRoot['To'] = recipients_str
    msgRoot.preamble = 'This is a multi-part message in MIME format.'
    msgRoot.set_charset('utf-8')

    msgAlternative = MIMEMultipart(_subtype='alternative')
    msgAlternative.set_charset("utf-8")
    msgRoot.attach(msgAlternative)

    msgText = MIMEText(_text=text_body, _subtype='plain', _charset='utf-8')
    msgAlternative.attach(msgText)

    html, images = extract_statics(html_body)
    attach_images(msgRoot, images)
    if attach:
        attach_images(msgRoot, attach)

    msgHtml = MIMEText(_text=html, _subtype='html', _charset='utf-8')
    msgAlternative.attach(msgHtml)

    if cfg['MAIL_ENABLED']:
        try:
            with smtplib.SMTP(
                    host=current_app.config['MAIL_SERVER'],
                    port=current_app.config['MAIL_PORT']) as smtp:
                if cfg['MAIL_TLS']:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.ehlo()
                    smtp.login(cfg['MAIL_USER'], cfg['MAIL_PASSWORD'])
                smtp.sendmail(
                    address(sender),
                    [address(r) for r in recipients],
                    msgRoot.as_string()
                )
        except Exception as e:
            if ignore_smtp_errors:
                current_app.logger.error(f'send_email() exception on smtplib.SMTP: {e}')
            else:
                raise

    if cfg.get('MAIL_ECHO', False):
        print('=== (disabled) MAIL FROM "%s" TO "%s"' % (address(sender), repr([address(r) for r in recipients])))
        print(msgRoot.as_string())


def bulk_send_email(subject, recipients, sender=None, attach=None,
                    html_body=None, text_body=None, template=None, **kwargs):
    """
    Отправка письма нескольким адресатам. Каждый получит свой собственный экземпляр.

    recipients - список
    attach - вложения, словарь имя-путь
    """
    if current_app.config['MAIL_ENABLED']:
        for recipient in recipients:
            send_email(subject, [recipient], sender, attach,
                       html_body, text_body, template, **kwargs)


def render_email(name, **kwargs):
    return (render_template(name + '.html', **kwargs),
            render_template(name + '.txt', **kwargs))