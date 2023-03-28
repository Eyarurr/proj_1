import datetime

from visual import create_app
from visual.core import db
from visual.models import User, TeamMember, AuthToken, Footage, Tour

USERS = {}
TOURS = {}
FOOTAGES = {}
STATUSES = Footage.STATUSES


def setup_module():
    """
    Создаёт в пустой базе юзеров:
    1. anna@biganto.com без ролей
    2. boris@biganto.com с ролями ('tours', 'users')
    3. cidor@biganto.com с ролями ('remote-processing')
    4. super@biganto.com с ролью ('super')
    5. banned@biganto.com c User.banned = True
    6. unconfirmed@biganto.com с User.email_confirmed = None
    7. deleted@biganto.com с User.deleted != None

    Каждому даёт по токену авторизации , равному User.email.
    :return:
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()

        users = [
            User(id=1, email='anna@biganto.com', email_confirmed=True, email_notifications=1, lang='ru'),
            User(id=2, email='boris@biganto.com', email_confirmed=True, team_member=TeamMember(roles=['tours', 'users'])),
            User(id=3, email='cidor@biganto.com', email_confirmed=True, team_member=TeamMember(roles=['remote-processing'])),
            User(id=4, email='super@biganto.com', email_confirmed=True, team_member=TeamMember(roles=['super'])),
            User(id=5, email='banned@biganto.com', email_confirmed=True, banned=True, team_member=TeamMember(roles=['remote-processing'])),
            User(id=6, email='unconfirmed@biganto.com', email_confirmed=False, team_member=TeamMember(roles=['remote-processing'])),
            User(id=7, email='deleted@biganto.com', email_confirmed=True, deleted=datetime.datetime.now(), team_member=TeamMember(roles=['remote-processing'])),
        ]
        for user in users:
            user.auth_tokens.append(AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30), ip='0.0.0.0'))
            db.session.add(user)
            db.session.flush()

            tour = Tour(id=user.id, user_id=user.id, title='tour',
                        footage=Footage(user_id=user.id, _status='testing', type='real'))
            db.session.add(tour)
            db.session.flush()
            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}
            TOURS[tour.id] = {k: getattr(tour, k) for k in ('id', 'user_id', 'title', 'hidden')}
            FOOTAGES[tour.id] = {k: getattr(tour.footage, k) for k in ('id', 'user_id', 'type', '_status')}

        db.session.commit()


def test_dataset_access(api):
    # Проверяем, что не проходят никакие запросы от анонимов забаненых, удалённых юзеров
    simple_dataset = {'type': 'filincam', 'id': 'id1'}

    resp = api.post('/remote-processing/datasets', simple_dataset)
    assert resp.status_code == 403

    resp = api.post('/remote-processing/datasets', simple_dataset, auth_as='banned@biganto.com')
    assert resp.status_code == 403

    resp = api.post('/remote-processing/datasets', simple_dataset, auth_as='unconfirmed@biganto.com')
    assert resp.status_code == 403

    # Пробуем создать другим юзерам датасет юзерами без нужных ролей
    resp = api.post('/remote-processing/datasets', {'type': 'filincam', 'id': 'a', 'user_id': 2}, auth_as='anna@biganto.com')
    assert resp.status_code == 403

    resp = api.post('/remote-processing/datasets', {'type': 'filincam', 'id': 'a', 'user_id': 1}, auth_as='boris@biganto.com')
    assert resp.status_code == 403

    # То же самое, но методом PUT
    resp = api.put('/remote-processing/datasets/filincam/a', simple_dataset)
    assert resp.status_code == 403

    resp = api.put('/remote-processing/datasets/filincam/a', simple_dataset, auth_as='banned@biganto.com')
    assert resp.status_code == 403

    resp = api.put('/remote-processing/datasets/filincam/a', simple_dataset, auth_as='unconfirmed@biganto.com')
    assert resp.status_code == 403

    resp = api.put('/remote-processing/datasets/filincam/a', {'type': 'filincam', 'id': 'a', 'user_id': 2}, auth_as='anna@biganto.com')
    assert resp.status_code == 403

    resp = api.put('/remote-processing/datasets/filincam/a', {'type': 'filincam', 'id': 'a', 'user_id': 1}, auth_as='boris@biganto.com')
    assert resp.status_code == 403

    # @todo: Сейчас не очень понятно, разрешать ли создавать датасеты для удалённых юзеров?
    # resp = api.post('/remote-processing/datasets', simple_dataset, username='deleted@biganto.com')
    # assert resp.status_code == 403

    # Читаем обычным юзером чужие датасеты
    resp = api.get('/remote-processing/datasets', auth_as='boris@biganto.com', query_string={'user_id': 1})
    assert resp.status_code == 403

    # Читаем привилегированным юзером чужие датасеты
    resp = api.get('/remote-processing/datasets', auth_as='cidor@biganto.com', query_string={'user_id': 1})
    assert resp.status_code == 200


def test_post_dataset(api):
    """
    Создать датасет
    POST /remote-processing/datasets
    тело
    {
    id: str
    type: str Тип датасета. Возможные значения: filincam — сцена Филинкама.
    user_id: int? = null
    User.id хозяина датасета. Редкий случай, когда user_id == null, означает, что датасет не принадлежит никому.
    title: str? = null Название датасета. Определяется удалённой системой. Может быть равным null в случае недобросовестной удалённой системы.
    props: object? = null Произвольный объект, описывающий характеристики датасета. Свойства объекта зависят от типа датасета.
    last_event: object? = null Объект последнего пришедшего события (RemoteEvent) над датасетом (если событий не приходило, то тут будет лежать  null).
    }
    """

    # Создаём датасет для себя с явным указанием user_id
    resp = api.post('/remote-processing/datasets', {'type': 'filincam', 'id': 'a', 'user_id': 1}, auth_as='anna@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert resp.result['type'] == 'filincam'
    assert resp.result['id'] == 'a'
    assert resp.result['user_id'] == 1

    # Создаём датасет для себя без явного указания user_id.
    resp = api.post('/remote-processing/datasets', {'type': 'filincam', 'id': 'a'}, auth_as='anna@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert resp.result['user_id'] == 1
    # ID был уже существующего датасета, поэтому проверяем, есть ли warning
    assert resp.has_warning('exists')

    # Теперь пробуем юзерами с нужными ролями (`remote-processing`, `super`) создавать датасеты для других юзеров
    resp = api.post('/remote-processing/datasets',
                    {'type': 'filincam', 'id': 'ba/ba', 'user_id': 2, 'title': 'Целуйте бабы рельсы я еду домой',
                     'props': {'a': 1}, 'foo': 'bar'},
                    auth_as='cidor@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert resp.result['user_id'] == 2
    assert resp.result['title'] == 'Целуйте бабы рельсы я еду домой'
    assert 'props' in resp.result
    assert resp.result['props'].get('a') == 1
    assert 'foo' not in resp.result

    resp = api.post('/remote-processing/datasets', {'type': 'filincam', 'id': 'co/co', 'user_id': 1}, auth_as='super@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert resp.result['user_id'] == 1

    # Проверки на входные данные датасета, создаём себе
    resp = api.post('/remote-processing/datasets', {'type': 'filincam' * 10, 'id': 'id1'}, auth_as='anna@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Dataset.type')

    resp = api.post('/remote-processing/datasets', {'type': 'filincam', 'id': 'id1' * 100}, auth_as='anna@biganto.com')
    assert resp.status_code == 400
    assert resp.has_error('Dataset.id')


def test_put_dataset(api):
    """
    Изменить датасет
    PUT /remote-processing/datasets/<dataset_type>/<dataset_id>

    Состояние: К началу этого теста, в test_post_datasets должно быть создано 3 датасета:
    filincam/a, anna@biganto.com
    filincam/ba/ba, boris@biganto.com, title="Целуйте бабы рельсы", props={'a': 1}
    filincam/co/co, anna@biganto.com
    """
    # Пробуем обновить несуществующий датасет
    resp = api.put('/remote-processing/datasets/unknown/z', {'title': 'Это несуществующий датасет.'}, auth_as='cidor@biganto.com')
    assert resp.status_code == 200
    assert resp.has_warning('was created')
    assert resp.result and resp.result['type'] == 'unknown' and resp.result['id'] == 'z'

    # Изменяем существующий датасет
    resp = api.put('/remote-processing/datasets/filincam/ba/ba', {'title': 'Я еду домой', 'props': {'foo': 'bar'}}, auth_as='cidor@biganto.com')
    assert resp.status_code == 200
    assert resp.result
    assert resp.result['title'] == 'Я еду домой'
    assert resp.result['props'] == {'foo': 'bar'}


def test_delete_dataset(api):
    """
    Удалить датасет
    DELETE /remote-processing/datasets/<dataset_type>/<dataset_id>

    Состояние: К началу этого теста, в test_post_datasets должно быть создано 4 датасета:
    filincam/a, anna@biganto.com
    filincam/ba/ba, boris@biganto.com, title="Целуйте бабы рельсы", props={'a': 1}
    filincam/co/co, anna@biganto.com
    unknown/z, cidor@biganto.com, title="Это несуществующий датасет."
    """
    # Удаляем датасет, к которому у нас нет прав доступа, обычным юзером
    resp = api.delete('/remote-processing/datasets/filincam/ba/ba', auth_as='anna@biganto.com')
    assert resp.status_code == 404

    # Удаляем несуществующий датасет привилегированным юзером
    resp = api.delete('/remote-processing/datasets/filincam/x', auth_as='cidor@biganto.com')
    assert resp.status_code == 404

    # Удаляем свой датасет (a) обычным юзером
    resp = api.delete('/remote-processing/datasets/filincam/a', auth_as='anna@biganto.com')
    assert resp.status_code == 204

    # Удаляем чужой датасет (b) привилегированным юзером
    resp = api.delete('/remote-processing/datasets/filincam/ba/ba', auth_as='cidor@biganto.com')
    assert resp.status_code == 204


def test_dataset_post_event(api):
    """
    Отправить событие
    POST /remote-processing/datasets/<dataset_type>/<dataset_id>/events
    Тело:
    {
    type: str Тип события. Возможные значения зависят от типа датасета.
    job_id: int? = null Идентификатор задачи при параллельных вычислениях.
    ts: datetime? = nullВремя наступления события.
    meta: object? = null Подробности события. Объект произвольной структуры, все поля не обязательные.
    }

    Состояние: К началу этого теста в базе должно остаться 2 датасета:
    filincam/co/co, anna@biganto.com
    unknown/z, cidor@biganto.com, title="Это несуществующий датасет."
    """

    # Постим евент от непривилегированного юзера к чужому датасету
    resp = api.post('/remote-processing/datasets/filincam/a/events', {}, auth_as='boris@biganto.com')
    assert resp.status_code == 404

    # Постим евент от привилегированного юзера к несуществующему датасету
    resp = api.post('/remote-processing/datasets/filincam/new/events', {'type': 'upload.started'}, auth_as='cidor@biganto.com')
    assert resp.status_code == 404

    # Следующая проверка — если решим, что POST .../events для несуществующего датасета создаёт датасет (это спорная идея)
    # if False:
    #     assert resp.has_warning('created')

    # Постим евент от непривилегированного юзера к своему датасету
    resp = api.post('/remote-processing/datasets/filincam/co/co/events', {'type': 'upload.started'}, auth_as='anna@biganto.com')
    assert resp.status_code == 200

    # Постим евент от привилегированного юзера к чужому датасету, со всеми правильными свойствами
    resp = api.post('/remote-processing/datasets/filincam/co/co/events',
                    {'type': 'upload.progress', 'job_id': 'abcdefg', 'ts': '2020-08-08T16:20:00',
                     'meta': {'progress': 0.5, 'eta': '2020-09-09T16:20:01', 'message': 'Живой я живой'}
                     },
                    auth_as='cidor@biganto.com'
                    )
    assert resp.status_code == 200

    # Проверяем уведомления. Постим евент transfer.success с инфой о туре в Event.meta и ждём, что
    # у юзера id=1 последнее уведомление будет об этом
    tour_id = 3
    resp = api.post('/remote-processing/datasets/filincam/co/co/events',
                    {
                        'type': 'transfer.success', 'job_id': 'abcdefg', 'ts': '2020-08-08T16:20:00',
                        'meta': {'results': [{'entity_id': tour_id, 'entity_type': 'tour'}]}
                    },
                    auth_as='cidor@biganto.com'
                    )
    assert resp.status_code == 200

    # И без указания тура в Event.meta
    resp = api.post('/remote-processing/datasets/filincam/co/co/events',
                    {
                        'type': 'transfer.success', 'job_id': 'abcdefg', 'ts': '2020-08-08T16:20:00',
                        'meta': {'results': [{}]}
                    },
                    auth_as='cidor@biganto.com'
                    )
    assert resp.status_code == 200

    # processing.failed
    resp = api.post('/remote-processing/datasets/filincam/co/co/events',
                    {
                        'type': 'processing.failed', 'job_id': 'abcdefg', 'ts': '2020-08-08T16:20:00',
                        'meta': {
                            'errors': ['Начнём с того.', 'Что ты пиздоглазое мудило.', 'А сцена так и вообще говно.'],
                            'warnings': ['Да и вообще как-то всё неспокойно.']
                        }
                    },
                    auth_as='cidor@biganto.com'
                    )
    assert resp.status_code == 200


def test_get_datasets(api):
    """К началу этого теста в базе должно остаться 2 датасета:
    filincam/co/co, anna@biganto.com
    unknown/z, cidor@biganto.com, title="Это несуществующий датасет."
    """
    # Добавляем ещё евентов датасету filincam/co/co
    resp = api.post('/remote-processing/datasets/filincam/co/co/events', {'type': 'upload.started'}, auth_as='anna@biganto.com')
    assert resp.status_code == 200
    resp = api.post('/remote-processing/datasets/filincam/co/co/events', {'type': 'upload.progress', 'meta': {'progress': 10}}, auth_as='anna@biganto.com')
    assert resp.status_code == 200
    resp = api.post('/remote-processing/datasets/filincam/co/co/events', {'type': 'upload.progress', 'meta': {'progress': 50}}, auth_as='anna@biganto.com')
    assert resp.status_code == 200
    resp = api.post('/remote-processing/datasets/filincam/co/co/events', {'type': 'upload.success'}, auth_as='anna@biganto.com')
    assert resp.status_code == 200

    # И нахуярим датасетов для anna@biganto.com для проверки сортировки
    resp = api.post('/remote-processing/datasets', {'type': 'filincam', 'id': 'new1', 'title': 'Первый новый', 'user_id': 1}, auth_as='anna@biganto.com')
    assert resp.status_code == 200
    resp = api.post('/remote-processing/datasets', {'type': 'filincam', 'id': 'new2', 'title': 'Второй новый', 'user_id': 1}, auth_as='anna@biganto.com')
    assert resp.status_code == 200
    resp = api.post('/remote-processing/datasets', {'type': 'filincam', 'id': 'new3', 'title': 'Третий новый', 'user_id': 1}, auth_as='anna@biganto.com')
    assert resp.status_code == 200
    resp = api.post('/remote-processing/datasets', {'type': 'filincam', 'id': 'new4', 'title': 'Четвёртый новый', 'user_id': 1}, auth_as='anna@biganto.com')
    assert resp.status_code == 200

    # Обычный запрос датасетов
    resp = api.get('/my/remote-processing/datasets', auth_as='anna@biganto.com')
    assert resp.status_code == 200
    
    assert resp.result
    assert type(resp.result) is list
    assert resp.result[0]['id'] == 'new4'
    assert resp.result[1]['id'] == 'new3'
    assert resp.result[2]['id'] == 'new2'
    assert resp.result[3]['id'] == 'new1'
    assert resp.result[4]['id'] == 'co/co'
    assert resp.result[0]['last_event'] is None
    assert type(resp.result[4]['last_event']) is dict

    # ?offset, ?limit
    resp = api.get('/my/remote-processing/datasets', auth_as='anna@biganto.com', query_string={'offset': 1, 'limit': 2})
    assert resp.status_code == 200
    
    assert len(resp.result) == 2
    assert resp.result[0]['id'] == 'new3'
    assert resp.result[1]['id'] == 'new2'

    # ?sort=title
    resp = api.get('/my/remote-processing/datasets', auth_as='anna@biganto.com', query_string={'sort': 'title'})
    assert resp.status_code == 200
    
    assert resp.result[0]['id'] == 'new2'
    assert resp.result[1]['id'] == 'new1'
    assert resp.result[2]['id'] == 'new3'
    assert resp.result[3]['id'] == 'new4'
    assert resp.result[4]['id'] == 'co/co'

    # ?sort=-title
    resp = api.get('/my/remote-processing/datasets', auth_as='anna@biganto.com', query_string={'sort': '-title'})
    assert resp.status_code == 200
    
    assert resp.result[0]['id'] == 'new4'
    assert resp.result[1]['id'] == 'new3'
    assert resp.result[2]['id'] == 'new1'
    assert resp.result[3]['id'] == 'new2'
    assert resp.result[4]['id'] == 'co/co'  # Датасеты без названия один хрен будут в конце списка из-за NULLS LAST в сортировке

    # ?sort=-last_event.created
    resp = api.get('/my/remote-processing/datasets', auth_as='anna@biganto.com', query_string={'sort': '-last_event.created'})
    assert resp.status_code == 200
    
    assert resp.result[0]['id'] == 'co/co'
    assert resp.result[1]['id'] == 'new4'
    assert resp.result[2]['id'] == 'new3'
    assert resp.result[3]['id'] == 'new2'
    assert resp.result[4]['id'] == 'new1'

    # ?sort=last_event.created
    resp = api.get('/my/remote-processing/datasets', auth_as='anna@biganto.com', query_string={'sort': 'last_event.created'})
    assert resp.status_code == 200
    
    assert resp.result[0]['id'] == 'new1'
    assert resp.result[1]['id'] == 'new2'
    assert resp.result[2]['id'] == 'new3'
    assert resp.result[3]['id'] == 'new4'
    assert resp.result[4]['id'] == 'co/co'


def test_events_bad_input(api):
    # Хуёвые евенты!
    # ...отсутствует Event.type
    resp = api.post('/remote-processing/datasets/unknown/z/events', {}, auth_as='cidor@biganto.com')
    assert resp.status_code == 400
    
    assert resp.has_error('Event.type')

    # ...неправильный тип  Event.type
    resp = api.post('/remote-processing/datasets/unknown/z/events', {'type': False}, auth_as='cidor@biganto.com')
    assert resp.status_code == 400
    
    assert resp.has_error('Event.type')

    # ...слишком длинный Event.type
    resp = api.post('/remote-processing/datasets/unknown/z/events', {'type': 'a' * 1000}, auth_as='cidor@biganto.com')
    assert resp.status_code == 400
    
    assert resp.has_error('Event.type')

    # ...неподдерживаемый Event.type
    resp = api.post('/remote-processing/datasets/unknown/z/events', {'type': 'punks not dead'}, auth_as='cidor@biganto.com')
    assert resp.status_code == 200
    
    assert resp.has_warning('not supported')

    # ...слишком длинный Event.job_id
    resp = api.post('/remote-processing/datasets/unknown/z/events', {'type': 'upload.paused', 'job_id': 'a' * 1000},
                    auth_as='cidor@biganto.com')
    assert resp.status_code == 400
    
    assert resp.has_error('Bad Event.job_id value. Should be string shorted than 128 bytes.')

    # ...хуйня в Event.ts
    resp = api.post('/remote-processing/datasets/unknown/z/events', {'type': 'upload.paused', 'ts': 'Дуров, верни стену!'}, auth_as='cidor@biganto.com')
    assert resp.status_code == 400
    
    assert resp.has_error('Event.ts')

    # ...хуйня в Event.meta
    resp = api.post('/remote-processing/datasets/unknown/z/events', {'type': 'upload.paused', 'meta': 'Боже, царя храни!'}, auth_as='cidor@biganto.com')
    assert resp.status_code == 400
    
    assert resp.has_error('Event.meta')


def test_datasets_bad_input(api):
    # Хуёвые параметры запросов на получение датасетов
    resp = api.get('/remote-processing/datasets', auth_as='cidor@biganto.com', query_string={'user_id': 'xx'})
    assert resp.status_code == 400

    resp = api.get('/remote-processing/datasets', auth_as='cidor@biganto.com', query_string={'user_id': '1', 'sort': 'zhopa'})
    assert resp.status_code == 400

    resp = api.get('/remote-processing/datasets', auth_as='cidor@biganto.com', query_string={'user_id': '1', 'offset': '-100'})
    assert resp.status_code == 400

    resp = api.get('/remote-processing/datasets', auth_as='cidor@biganto.com', query_string={'user_id': '1', 'limit': '100500'})
    assert resp.status_code == 400
