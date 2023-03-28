'use strict';

$(function() {

    /**
     * Модуль табличного вывода общей статистики над графиком
     */
    BG.tableSum = (function() {
        var person = {},
            common = {},

            // const
            BC = 'table-sum',
            configColumns,

            // dom
            parent = $('.' + BC),
            inner;

        function prepareDOM() {

            inner = $('.' + BC + '__inner', parent);
        };

        function setConstants() {

            configColumns = {
                traffic: [],
                geo: [],
                time: [
                    [
                        'label',
                        ''      //'Название тура/объекта'
                    ],
                    [
                        'time_med',
                        BG.CONST.STAT.FIELDS['median']
                    ],
                    [
                        'time_max',
                        BG.CONST.STAT.FIELDS['maximum']
                    ]
                ],
                sources: []
            };
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
         * @param {string} type Тип данных: traffic, geo, time, sources
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
            estates = BG.tmpl.other['tmpl__table-sum-' + type]($.extend({}, dataRender, {type: 'estates'}));
            tours = BG.tmpl.other['tmpl__table-sum-' + type]($.extend({}, dataRender, {type: 'tours'}));

            // добавляем к таблице шапку
            inner.html(BG.tmpl.other['tmpl__table-sum']({
                columns: dataInput.columns,
                tours: tours,
                estates: estates,
                count: count
            }));
        };

        common.init = function() {

            if (!parent.length) return;

            setConstants();
            prepareDOM();
        };

        /**
         * Обновление таблицы (следует вызывать лишь при получении новых данных)
         * @param {string} type Тип запроса: traffic, geo, time, sources
         * @param {object} dataInput Сырые данные
         * @param {object} params Параметры, с которыми был сделан запрос
         */
        common.update = function(type, dataInput, params) {
            var data = {};

            // проверка на необходимость показа таблицы
            if (!configColumns[type].length) {
                common.hide();
                return;
            }

            data['data'] = dataInput;
            data['columns'] = configColumns[type];

            render(type, data, params);
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

    BG.tableSum.init();
});