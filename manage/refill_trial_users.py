from visual.core import db, products


class RefillTrialUsers:
    """Раздаёт всем Trial-юзерам виртостера положенное число сборок на месяц. Запускается 1-го числа каждого месяца."""

    def run(self):
        db.session.execute(
            "UPDATE user_products SET meta = jsonb_set(meta, '{processings_left}', ':n') WHERE plan_id = 0",
            {'n': products.virtoaster.plans[0].meta['processings']}
        )
        db.session.commit()
