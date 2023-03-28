from visual import create_app
from visual.core import db
from visual.models import Tag
from ..common import create_users, create_estate, create_tags


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

        # Теги
        tag_ids = create_tags(1, ['area', 'price', 'floor', 'floors', 'description', 'ghosts'])

        # Эстейты
        estates = [
            (1, dict(area=10, price=1000, floor=1, floors=3, description='This flat is ten meters')),
            (2, dict(area=20, price=2000, floor=1, floors=3, description='This flat is twenty meters')),
            (3, dict(area=30, price=3000, floor=2, floors=2, description='This flat is thirty meters')),
            (4, dict(area=40, price=4000, floor=2, floors=3, description='This office is 2 x twenty meters')),
            (5, dict(area=50, price=5000, floor=3, floors=3, description='This office is fifty meters', ghosts=None)),
            (6, dict(area=60, price=6000, floor=3, floors=1, description='This bar is great', ghosts=None)),
        ]
        for estate_id, tags in estates:
            create_estate({'id': estate_id, 'user_id': 1, 'title': f'Estate {estate_id}', 'tags': tags}, tag_ids)

        db.session.commit()


def test_tfilter(api):
    # [(tfilter, expected), ...]
    cases = [
        ('#nonexistent', []),
        ('#ghosts', [5, 6]),
        ('#floor=2', [3, 4]),
        ('#floor!=2', [1, 2, 5, 6]),
        ('#floor>2', [5, 6]),
        ('#floor>=2', [3, 4, 5, 6]),
        ('#floor<2', [1, 2]),
        ('#floor<=2', [1, 2, 3, 4]),
        ('#floor=#floors', [3, 5]),
        ('#floor!=#floors', [1, 2, 4, 6]),
        ('#floor>#floors', [6]),
        ('#floor>#nonexistent', []),
        ('#description~twenty meters', [2, 4]),
        ('#description~', [1, 2, 3, 4, 5, 6]),
    ]
    for tfilter, expected in cases:
        resp = api.get(f'/my/estates', auth_as='user1@biganto.com', query_string={'tfilter': tfilter, 'total': 1})
        assert resp.status_code == 200, f'{tfilter}: {resp.object}'
        assert sorted([x['id'] for x in resp.result]) == sorted(expected), f'{tfilter} expected {expected}'
        assert resp.pagination['total'] == len(expected)


