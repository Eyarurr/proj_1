from datetime import datetime

from pydantic import BaseModel, PrivateAttr
from visual.util import dict_merge


class UserSettingsBase(BaseModel):
    def merge(self, src):
        """Обновляет себя из словаря src (deep merge)."""
        d = self.dict()
        dict_merge(d, src)
        self.__init__(**d)
        return

        print(f'\nmerge({self.__class__.__name__}, {src})')
        for k, v in src.items():
            print('> ', k, type(getattr(self, k)), isinstance(getattr(self, k), UserSettingsBase), type(v))

            if isinstance(getattr(self, k), UserSettingsBase):
                getattr(self, k).merge(v)
            else:
                setattr(self, k, v)

    def clone(self):
        new = self.__class__(**self.dict())
        return new


class USFilincamTour(UserSettingsBase):
    enabled: bool = True
    folder_id: int = None
    title: str = None
    blur_faces: bool = True
    blur_plates: bool = False


class USFilincam(UserSettingsBase):
    autoprocess: bool = True
    export_tour: USFilincamTour = USFilincamTour()


class USDomHubRequest(UserSettingsBase):
    method: str = 'GET'
    url: str = None
    headers: dict = {}


class USDomHubRequestIndex(USDomHubRequest):
    key_id: str = None
    key_title: str = None


class USDomHubCrm(UserSettingsBase):
    headers: dict = {}
    get_estate: USDomHubRequest = USDomHubRequest()
    get_estates_index: USDomHubRequestIndex = USDomHubRequestIndex()


class USDomHub(UserSettingsBase):
    crm: USDomHubCrm = USDomHubCrm()


class UserSettings(UserSettingsBase):
    news_last_seen: datetime = None
    filincam: USFilincam = USFilincam()
    domhub: USDomHub = USDomHub()
    _user = PrivateAttr()

    # def __init__(self, user, **data: Any):
    #     super().__init__(**data)
    #     self._user = user

    def as_dict(self, skip_defaults=False):
        return self.dict(exclude_defaults=skip_defaults)

    def clone(self):
        pass

    # def save(self):
    #     self._user.settings = self.dict(exclude_defaults=True)
    #     flag_modified(self._user, 'settings')


