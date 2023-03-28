from requests import request
import json
from urllib.parse import urljoin, urlparse, parse_qsl
import logging

from flask import current_app


log = logging.getLogger('filincam')


def api_request(method, endpoint, body):
    """Делает запрос к API филинкама"""
    qs_endpoint = dict(parse_qsl(urlparse(endpoint).query))

    query_string = {
        'client': 'biganto_server',
        'client_version': '1.0.0',
        'access_token': current_app.config['FILINCAM_API_KEY']
    }
    query_string.update(qs_endpoint)

    headers = {
        'Content-Type': 'application/json'
    }

    url = urljoin(current_app.config['FILINCAM_API_HOST'], endpoint)
    log.debug(f'SEND REQUEST TO PROCESSING {method} {url}:')
    log.debug(json.dumps(body, indent=4, ensure_ascii=False))

    res = request(method, url, json=body, headers=headers, params=query_string)
    log.debug(f'Response: {res.status_code}')
    if res.ok:
        log.debug(res.text)
    else:
        log.error(res.text)

    return res
