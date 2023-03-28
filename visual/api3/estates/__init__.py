import re

from visual.models import Tag, Estate, EstateAsset, EstateTag
from visual.core import db

ASSETS_SORTS = {
    'created': EstateAsset.created,
    'title': EstateAsset.title,
    'type': EstateAsset.type,
    'size': EstateAsset.size,
    'sort': EstateAsset.sort,
}


class TFilter:
    """Класс парсит синтаксис фильтра ?tfilter и умеет применять эту логику к Query."""
    def __init__(self, arg):
        r = re.match(r'^#(\w+)$', arg)
        if r:
            self.tagname = r.group(1)
            self.op = None
            self.val = None
        else:
            r = re.match(r'^#(\w+)(>=|<=|!=|>|<|=|~)(.*)$', arg)
            if not r:
                raise ValueError('Invalid tfilter syntax')
            self.tagname = r.group(1)
            self.op = r.group(2)
            self.val = r.group(3)

    def apply_to_query(self, q):
        """Применяет к запросу `q` условия, чтобы фильтровать по tfilter"""
        q = q.join(EstateTag).join(Tag).filter(Tag.name == self.tagname)

        if self.op is None:
            return q

        if self.op == '~':
            return q.filter(EstateTag.value.like('%' + self.val + '%'))

        cmp_ops = ('=', '!=', '>', '>=', '<', '<=')
        if self.op in cmp_ops:
            if self.val.startswith('#'):
                # #tagname <op> #tagname
                tag2name = self.val[1:]
                et2 = db.aliased(EstateTag)
                t2 = db.aliased(Tag)
                expressions = {
                    '=': db.func.graceful_int(EstateTag.value) == db.func.graceful_int(et2.value),
                    '!=': db.func.graceful_int(EstateTag.value) != db.func.graceful_int(et2.value),
                    '>': db.func.graceful_int(EstateTag.value) > db.func.graceful_int(et2.value),
                    '>=': db.func.graceful_int(EstateTag.value) >= db.func.graceful_int(et2.value),
                    '<': db.func.graceful_int(EstateTag.value) < db.func.graceful_int(et2.value),
                    '<=': db.func.graceful_int(EstateTag.value) <= db.func.graceful_int(et2.value),
                }
                q = q\
                    .outerjoin(et2, et2.estate_id == Estate.id)\
                    .outerjoin(t2, t2.id == et2.tag_id)\
                    .filter(t2.name == tag2name, expressions[self.op])
                return q
            else:
                # #tagname <op> <value>
                try:
                    val = int(self.val)
                except ValueError:
                    raise ValueError('Non-int value for comparison')
                expressions = {
                    '=': db.func.graceful_int(EstateTag.value) == val,
                    '!=': db.func.graceful_int(EstateTag.value) != val,
                    '>': db.func.graceful_int(EstateTag.value) > val,
                    '>=': db.func.graceful_int(EstateTag.value) >= val,
                    '<': db.func.graceful_int(EstateTag.value) < val,
                    '<=': db.func.graceful_int(EstateTag.value) <= val,
                }
                q = q.filter(expressions[self.op])
                return q

        raise ValueError(f'Unknown operator: "{self.op}"')


from . import estates, assets, tags

