from visual import create_app
from visual.core import db
from visual.models import Tag
from ..common import create_users, create_tags, create_estate


def setup_module():
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()

        db.session.execute('''
CREATE OR REPLACE FUNCTION graceful_int(v_input text)
RETURNS INTEGER AS $$
DECLARE v_int_value INTEGER DEFAULT NULL;
BEGIN
    BEGIN
        v_int_value := v_input::INTEGER;
    EXCEPTION WHEN OTHERS THEN
        RETURN NULL;
    END;
RETURN v_int_value;
END;
$$ LANGUAGE plpgsql;
        ''')

        create_users({
            1: dict(email='user1@biganto.com'),
        })
        db.session.flush()

        tag_ids = create_tags(1, ['area', 'price', 'description'])

        # Эстейты
        create_estate({
            'id': 1,
            'user_id': 1,
            'title': 'Estate 1',
            'tags': {
                'area': 10,
                'price': 100,
                'description': 'text descr 1'
            }
        }, tag_ids)

        create_estate({
            'id': 2,
            'user_id': 1,
            'title': 'Estate 2',
            'tags': {
                'area': 20,
                'price': 200,
                'description': 'text descr 2'
            }
        }, tag_ids)

        create_estate({
            'id': 3,
            'user_id': 1,
            'title': 'Estate 3',
            'tags': {
                'area': -10,
                'price': 300,
                'description': 'text descr 2'
            }
        }, tag_ids)
        db.session.commit()


def test_tags_ranges(api):
    # [(?tags, expected), ...]
    cases = [
        (None, {'area': {'min': -10, 'max': 20}, 'price': {'min': 100, 'max': 300}, 'description': {'min': None, 'max': None}}),
        ('area', {'area': {'min': -10, 'max': 20}}),
        ('area,price', {'area': {'min': -10, 'max': 20}, 'price': {'min': 100, 'max': 300}}),
    ]
    for tags, expected in cases:
        resp = api.get(f'/my/estates/tags/ranges', auth_as='user1@biganto.com', query_string={'tags': tags})
        assert resp.status_code == 200, f'{tags}: {resp.object}'
        assert resp.result == expected, f'{tags}'


