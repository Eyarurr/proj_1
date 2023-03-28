'use strict';

$(function() {

    /**
     * Модуль табличного вывода статистики
     */
    BG.tableStat = (function() {
        var person = {},
            common = {},

            // const
            BC = 'table-stat',
            clOpen = 'is-open',
            clHidden = 'is-hidden',
            configColumns,

            // dom
            d = BG.STORE.dom.d,
            w = BG.STORE.dom.w,
            b = BG.STORE.dom.b,

            parent = $('.' + BC),
            form,
            head,
            th,

            // vars
            isFirstRender = true;

        /**
         * Определение заголовков таблиц для каждого типа статистики
         * @return {void}
         */
        function setConfig() {

            configColumns = {
                traffic: [
                    [
                        'label',
                        ''
                    ],
                    [
                        'visits',
                        BG.CONST.STAT.FIELDS['visits'],
                        0
                    ],
                    [
                        'users',
                        BG.CONST.STAT.FIELDS['users'],
                        1
                    ]
                ],
                geo: [
                    [
                        'country',
                        BG.CONST.STAT.FIELDS['city_country']
                    ],
                    [
                        'visits',
                        BG.CONST.STAT.FIELDS['visits']
                    ]
                ],
                time: [
                    [
                        'label',
                        ''
                    ],
                    [
                        'visits',
                        BG.CONST.STAT.FIELDS['visits']
                    ]
                ],
                sources: [
                    [
                        'referer_host',
                        BG.CONST.STAT.FIELDS['referer_host']
                    ],
                    [
                        'iframe',
                        BG.CONST.STAT.FIELDS['iframe']
                    ],
                    [
                        'visits',
                        BG.CONST.STAT.FIELDS['visits']
                    ]
                ]
            };
        };

        function prepareDOM() {

            form = $('.' + BC + '__form', parent);
        };

        function updateDOM() {

            head = $('.' + BC + '__head', parent);
            th = $('th', head);
        };

        function bindEvents() {

            b.on('click', '.' + BC + '__checkbox input[type="checkbox"]', function(e) {

                if (BG.categoryList.getCount() > 1) return;
                BG.chart.update();
            });

            b.on('click', '.' + BC + '__title', function(e) {
                var self = $(this);
                self
                    .toggleClass(clOpen)
                    .next('.' + BC + '__body').toggleClass(clHidden);
            });
        };

        /**
         * Предварительная подготовка данных
         * @return {object}
         */
        function prepareData(type, dataInput) {
            var result = {};

            result['data'] = dataInput;
            result['columns'] = configColumns[type];

            return result;
        };

        /**
         * Возвращает количество туров и объектов
         * @param {object} Данные для рендеринга таблицы
         * @return {object}
         */
        function getCounter(dataInput) {
            var result = {};

            result.columns = dataInput.columns.length;
            result.estates = _.keys(dataInput.data.estates).length;
            result.tours = _.keys(dataInput.data.tours).length;
            result.all = result.estates + result.tours;
            result.existBoth = result.estates > 0 && result.tours > 0;

            return result;
        };

        /**
         * Рендер данных
         * @param {string} type Тип данных
         * @param {array} dataInput Объект с данными
         * @param {object} params Параметры, с которыми был сделан запрос
         * @return {void}
         */
        function render(type, dataInput, params) {
            var result = dataInput,
                dataRender,
                estates,
                tours,
                count;

            // счетчики количества туров и объектов
            count = getCounter(dataInput);
            // данные для рендера
            dataRender = $.extend(result, {params: params, count: count});

            // готовим html туров и объектов
            // данные передаются в шаблон в виде:
            // { data: Object, columns: Object, params: Object, count: Object, type: String }
            estates = BG.tmpl.other['tmpl__table-' + type]($.extend({}, dataRender, {type: 'estates'}));
            tours = BG.tmpl.other['tmpl__table-' + type]($.extend({}, dataRender, {type: 'tours'}));

            // добавляем к таблице шапку
            form.html(BG.tmpl.other['tmpl__table-stat']({
                columns: dataInput.columns,
                tours: tours,
                estates: estates,
                count: count
            }));
        };

        common.init = function() {

            if (!parent.length) return;

            setConfig();
            prepareDOM();
            bindEvents();

            isFirstRender = false;
        };

        /**
         * Возвращает массив включенных колонок
         * на основе значения атрибута checked инпутов типа checkbox
         * @return {array / null}
         */
        common.getEnabledColumns = function() {
            var checks = $('input[type="checkbox"]', th);
            return checks.length ? $.map(checks, function(value, index) {
                        return $(value).prop('checked') ? $(value).prop('name') : null;
                    }) : null;
        };

        /**
         * Обновление таблицы (следует вызывать лишь при получении новых данных)
         * @param {string} typeStat Тип запроса: traffic, geo, time, sources
         * @param {object} dataInput Ответ от API
         * @param {object} params Параметры, с которыми был сделан запрос
         */
        common.update = function(typeStat, dataInput, params) {
            var dataFlow,
                preparedData;

            // распарсиваем данные в нужную структуру
            preparedData = BG.parser.table[typeStat](dataInput, params);

            preparedData = {
                data: preparedData,
                columns: configColumns[typeStat]
            };

            render(typeStat, preparedData, params);
            updateDOM();
        };

        /**
         * Показать
         */
        common.show = function() {
            parent.show();
        };

        /**
         * Скрыть
         */
        common.hide = function() {
            parent.hide();
        };

        return common;
    })();

    BG.tableStat.init();
});