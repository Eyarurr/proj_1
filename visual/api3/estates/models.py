import typing
from pydantic import BaseModel, Extra, ValidationError, constr, validator


def split_arg(t: str):
    """Разбивает аргумент со значениями через запятые в список"""
    return t.split(',')


class TagInput(BaseModel):
    id: int = None
    name: constr(min_length=1, strip_whitespace=True) = None
    value: str = None


class PostEstatesInput(BaseModel, extra=Extra.forbid):
    """POST /my/estates3"""
    title: constr(min_length=1, strip_whitespace=True)
    remote_id: str = None
    tags: typing.List[TagInput] = None


class PutEstatesInput(PostEstatesInput, extra=Extra.forbid):
    """PUT /estates/<id>"""
    title: constr(min_length=1, strip_whitespace=True) = None


class GetEstateArgs(BaseModel):
    """GET /estates/<id>"""
    tags: typing.List[str] = None
    format_values: bool = None  # (all)
    group_tags: str = None  # (id, name)
    assets: typing.List[str] = None
    assets_sort: str = 'created'  # (created, title, type, size)

    _split_tags = validator('tags', pre=True, allow_reuse=True)(split_arg)
    _split_assets = validator('assets', pre=True, allow_reuse=True)(split_arg)


class GetEstatesArgs(GetEstateArgs):
    """GET /my/estates"""
    sort: str = '-created'  # (created, synced, title)
    tfilter: str = None

    _split_tags = validator('tags', pre=True, allow_reuse=True)(split_arg)
    _split_assets = validator('assets', pre=True, allow_reuse=True)(split_arg)


class PostAssetInput(BaseModel, extra=Extra.forbid):
    """POST /estates/<id>/assets"""
    type: str
    tour_id: int = None
    tour_video_id: int = None
    url: str = None
    title: str = None
    sort: int = None


class GetEstateAssetsArgs(BaseModel):
    """GET /estates/<id>/estates"""
    type: typing.List[str] = None
    sort: str = 'created'  # (created, type, title, size)

    _split_type = validator('type', pre=True, allow_reuse=True)(split_arg)


class PutEstateAssetInput(BaseModel, extra=Extra.forbid):
    """POST /estates/<id>/assets"""
    title: constr(min_length=1, strip_whitespace=True) = None
    sort: int = None


class PostAssetsFromBRAsset(BaseModel):
    """POST /estates/<id>/assets/from-br-asset"""
    force_synchronous: bool = False


class PostAssetsFromBROrder(BaseModel):
    """POST /estates/<id>/assets/from-br-order"""
    type: typing.List[str] = None
    ignore_existing: bool = False
    force_synchronous: bool = False

    _split_type = validator('type', pre=True, allow_reuse=True)(split_arg)


class GetEstateTagsArgs(BaseModel):
    """GET /estates/<id>/tags"""
    group_tags: str = None
    format_values: bool = None
    name: typing.List[str] = None

    @validator('group_tags', pre=True)
    def val_name(cls, v):
        if v not in ('id', 'name'):
            raise ValidationError('group_tags should be "id" or "name')
        return v

    _split_name = validator('name', pre=True, allow_reuse=True)(split_arg)


class GetEstatesTagsRanges(BaseModel):
    """GET /my/estates/tags/ranges"""
    tags: typing.List[str] = None

    _split_name = validator('tags', pre=True, allow_reuse=True)(split_arg)


class PostEstatesTagsInput(BaseModel, extra=Extra.forbid):
    """POST /estates/<id>/tags"""
    name: constr(min_length=1, strip_whitespace=True)
    value: str = None


class PutEstatesTagsInput(BaseModel, extra=Extra.forbid):
    """PUT /estates/<id>/tags/<id>"""
    value: str = None


__all__ = ['TagInput', 'PostAssetInput', 'PutEstatesInput', 'GetEstateArgs', 'GetEstatesArgs', 'PostEstatesInput', 'GetEstateAssetsArgs',
           'PutEstateAssetInput', 'PostAssetsFromBRAsset', 'PostAssetsFromBROrder', 'GetEstateTagsArgs', 'PutEstatesTagsInput', 'PostEstatesTagsInput',
           'GetEstatesTagsRanges']


