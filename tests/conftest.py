import os
import pytest
import json
import warnings
import datetime

from sqlalchemy.schema import DropTable
from sqlalchemy.ext.compiler import compiles

from visual import create_app
from visual.core import db
from visual.models import User, Footage, Tour
from visual.util import unzip_footage_tour

SRC_DIR = '/srv/biganto.com/tests/src'


# Костыль или багфикс, так как sqlalchemy.drop_all() не делает каскадного удаления
@compiles(DropTable, "postgresql")
def _compile_drop_table(element, compiler, **kwargs):
    return compiler.visit_drop_table(element) + " CASCADE"


def pytest_addoption(parser):
    parser.addoption("--skip-bad-requests", action="store_true", default=False, help='Пропускать тесты с плохими запросами')
    parser.addoption("--skip-access", action="store_true", default=False, help='Пропускать тесты на права доступа')


def pytest_configure(config):
    config.addinivalue_line("markers", "bad_requests: mark test as bad requests")
    config.addinivalue_line("markers", "access: mark test as access test")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--skip-bad-requests"):
        skip_bad = pytest.mark.skip(reason="Пропущено из-за --skip-bad-requests")
        for item in items:
            if "bad_requests" in item.keywords:
                item.add_marker(skip_bad)

    if config.getoption("--skip-access"):
        skip_access = pytest.mark.skip(reason="Пропущено из-за --skip-access")
        for item in items:
            if "access" in item.keywords:
                item.add_marker(skip_access)


class APIClient:
    """Клиент для запросов к API biganto.com."""
    def __init__(self, client, app):
        self.client = client
        self.app = app
        self._AUTH_TOKEN_CACHE = {}

    def request(self, method, endpoint, body=None, query_string=None, auth_as=None, _debug=False, **kwargs):
        """Совершает запрос к API от имени пользователя `auth_as` (там ожидается e-mail юзера).
        Возвращает экземпляр APIResponse."""
        """"""
        url = '/api/v3{}'.format(endpoint)

        kw = kwargs.copy()
        kw['method'] = method
        if body is not None:
            kw['json'] = body
        kw['query_string'] = {'client': 'pytest', 'client_version': '1.0.0'}
        if query_string is not None:
            kw['query_string'].update(query_string)
        if auth_as is not None:
            if auth_as not in self._AUTH_TOKEN_CACHE:
                with self.app.app_context():
                    user = User.query.filter_by(email=auth_as).first()
                    if not user:
                        raise ValueError('Юзер {} не найден.'.format(auth_as))
                    self._AUTH_TOKEN_CACHE[auth_as] = str(user.auth_tokens[0])
            kw['query_string']['auth_token'] = self._AUTH_TOKEN_CACHE[auth_as]

        if _debug:
            print('\nAPI REQUEST [{} {}] {}'.format(method, url, kw))

        t1 = datetime.datetime.now()
        rv = self.client.open(url, **kw)
        t2 = datetime.datetime.now()

        if _debug:
            print('HTTP STATUS: ', rv.status_code)
            print('HTTP RESPONSE HEADERS:')
            print(rv.headers)
            print('HTTP RESPONSE BODY:')
            if rv.headers.get('Content-Type') == 'application/json':
                resp = json.loads(rv.get_data(as_text=True))
                print(json.dumps(resp, indent=4, ensure_ascii=False))
            else:
                print(rv.get_data(as_text=True))
            print(f'Request Time: {t2 - t1}')

        return APIResponse(rv)

    def get(self, *args, **kwargs):
        return self.request('GET', *args, **kwargs)

    def post(self, *args, **kwargs):
        return self.request('POST', *args, **kwargs)

    def put(self, *args, **kwargs):
        return self.request('PUT', *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.request('DELETE', *args, **kwargs)


class APIResponse:
    """Обертка вокруг requests.Response с методами для работы с API biganto.com."""
    def __init__(self, rv):
        # requests.Response
        self._response = rv

        # json.loads(rv.get_data())
        self._response_object = None

    @property
    def object(self):
        """Возвращает объект ответа, кеширует его."""
        if self._response_object is None:
            self._response_object = json.loads(self._response.get_data(as_text=True))
        return self._response_object

    @property
    def result(self):
        """Возвращает свойство `result` ответа или None, если его в ответе не было."""
        if self.object is None:
            return None
        return self.object.get('result')

    @property
    def errors(self):
        """Возвращает свойство `errors` ответа или None, если его в ответе не было."""
        if self.object is None:
            return None
        return self.object.get('errors')

    @property
    def warnings(self):
        """Возвращает свойство `warnings` ответа или None, если его в ответе не было"""
        if self.object is None:
            return None
        return self.object.get('warnings')

    @property
    def pagination(self):
        """Возвращает свойство `warnings` ответа или None, если его в ответе не было"""
        if self.object is None:
            return None
        return self.object.get('pagination')

    def has_error(self, txt):
        """Проверяет, содержится ли в ошибках resp['errors'] подстрока `txt`"""
        assert type(self.object) is dict
        assert 'errors' in self.object
        for e in self.object['errors']:
            if txt in e:
                return True
        return False

    def has_warning(self, txt):
        """Проверяет, содержится ли в варнингах resp['warnings'] подстрока `txt`"""
        assert type(self.object) is dict
        assert 'warnings' in self.object
        for e in self.object['warnings']:
            if txt in e:
                return True
        return False

    def __getattr__(self, item):
        return getattr(self._response, item)


@pytest.fixture(scope='module')
def api():
    app = create_app('config.test.py')
    with app.test_client() as client:
        api_client = APIClient(client, app)
        yield api_client


@pytest.fixture(scope='module')
def app():
    app = create_app('config.test.py')
    yield app





# Ниже — OBSOLETE

@pytest.fixture(scope='module')
def client():
    app = create_app('config.test.py')
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

        yield client


@pytest.fixture(scope='module')
def users():
    app = create_app('config.test.py')
    with app.app_context():
        with open(os.path.join(SRC_DIR, 'users.json')) as fh:
            test_users = json.load(fh)

        for u in test_users:
            udata = u.copy()
            udata['password_hash'] = User.hash_password(udata['password'])
            del udata['password']
            user = User(**udata)
            db.session.add(user)
        db.session.commit()


@pytest.fixture(scope='module')
def tours(request):
    """Берёт туры, указанные в src_dir/tours.json и распаковывает их в туры для тестовой базы"""

    def fin():
        """Удаляем после себя созданные асеты"""
        app = create_app('config.test.py')
        with app.app_context():
            for item in Tour.query.all():
                item.delete()
            for item in Footage.query.all():
                item.delete()

    app = create_app('config.test.py')
    with app.app_context():
        with open(os.path.join(SRC_DIR, 'tours.json')) as fh:
            test_tours = json.load(fh)

        # Можно загрузить только один тур
        if hasattr(request, 'param') and request.param:
            test_tours = [test_tours[request.param]]
        for tour_data in test_tours:
            footage = Footage(meta={}, **tour_data['*footage'])
            db.session.add(footage)
            db.session.flush()
            tour = Tour(footage_id=footage.id, meta={}, **{k: v for k, v in tour_data.items() if not k.startswith('*')})
            db.session.add(tour)
            db.session.flush()
            footage.mkdir()
            tour.mkdir()
            wrns = unzip_footage_tour(os.path.join(SRC_DIR, tour_data['*zip']), footage, tour)
            db.session.commit()
            for w in wrns:
                warnings.warn('Распаковка тура {}: {}'.format(tour_data['*zip'], w))

        # Так как tours.id и footage.id ID могли быть указаны в tours.json принудительно, обновим секвенции tours_id_seq и footage_id_seq
        db.session.execute("""SELECT setval('tours_id_seq', (SELECT MAX(id) FROM tours))""")
        db.session.execute("""SELECT setval('footages_id_seq', (SELECT MAX(id) FROM footages))""")

    request.addfinalizer(fin)


@pytest.fixture(scope='function')
def del_trash():
    "Удалим лишние туры"
    app = create_app('config.test.py')
    with app.app_context():
        tours = db.session.query(Tour).filter(Tour.id >= 100)
        if tours:
            for tour in tours.all():
                tour.delete(check_orphan_footage=True)
        db.session.commit()
        db.session.execute("SELECT setval('tours_id_seq', 100)")
