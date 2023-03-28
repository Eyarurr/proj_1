import yaml
import logging
import os

from flask_script import Command

from visual.models import Partner
from visual.core import db


log = logging.getLogger(__name__)
log.setLevel(logging.WARNING)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class InitPartners(Command):
    def __init__(self, func=None):
        super().__init__(func)

    def run(self):
        self.clear_data()
        self.init_partners()

    def init_partners(self):
        for sort_num, partner_data in self.get_partners_data().items():
            partner = Partner(sort=sort_num,
                              hidden=partner_data.get('hidden', True),
                              title=partner_data.get('title', ''),
                              # url=partner_data.get('url', '')
                              )
            db.session.add(partner)
            db.session.flush()
            partner.logo = os.path.join(BASE_DIR, partner_data['logo'])
        db.session.commit()

    def get_partners_data(self):
        try:
            with open("manage/partners_data.yaml", 'r') as stream:
                return yaml.load(stream)
        except (FileNotFoundError, yaml.YAMLError) as exception:
            log.warning(exception)
            return {}

    def clear_data(self):
        for partner in Partner.query.all():
            del partner.logo
        db.session.query(Partner).delete()
