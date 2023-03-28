В папке srv/biganto.com/tests/src помимо users.json tours.json должны находиться main.mp3, panorama.png, panorama_binocular.png, stats.json. Архив с этими файлами лежит на Google Диск в файле src\files.zip. 
Папка tests/flow-upload/TOKEN пересоздается и заполняется тестовыми данными при запуске очередного модуля. 
Для запуска контроля code coverage должен быть установлен pytest-cov 2.12.1  https://pypi.org/project/pytest-cov/
Генерация HTML отчетов осуществляется: pytest --cov-report html:cov_html --cov=visual.api3

В conftest.py в фикстуре tours  request.addfinalizer(fin) удаляет после себя файлы асетов. 


--tb=[auto/long/short/line/native/no]: Управляет стилем трассировки.
-v / --verbose: Отображает все имена тестов, пройденных или не пройденных.
-l / --showlocals: Отображает локальные переменные рядом с трассировкой стека.
-lf / --last-failed: Запускает только тесты, которые завершились неудачей.
-x / --exitfirst: Останавливает тестовую сессию при первом сбое.
--pdb: Запускает интерактивный сеанс отладки в точке сбоя.
-s : выводит принты.

pytest test_api_actions.py::test_created_action_clickable_toggle_class -sv : Запуск одного теста в указанном модуле 




Финализация автотестов.
Вопросы
1. Есть методы и ендпоинты не описанные в wiki: 
GET /footages/<footage_id> метод 'cnt_skyboxes', 
GET /tours/<id>/files , 
/tours/<int:tour_id>/files', methods=('PUT', )
/tours/<int:tour_id>/files/<path:target>', methods=('DELETE',) - это что быстро вспомнил

2. С помощью : PUT /footages/<footage_id>.  и PUT  "/tours/1" с конструкцией json=
    {"title": 'Title2',
     'meta.shit': 'new tag'
     })
Пользователь может редактировать мету, добавлять новые теги, забивать всяким говном существующие теги. Мне поставить проверку, что мы позволяем добавит теги типа SHIT или не разрешить добавить такие тег? 




