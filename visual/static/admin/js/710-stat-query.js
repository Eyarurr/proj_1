'use strict';

$(function() {

    /**
     * Модуль запроса данных
     */

    BG.queryStat = (function() {
        var person = {},
            common = {},

            // const
            endpoint = '/my/statistics/api/',

            // dom
            d = BG.STORE.dom.d,
            w = BG.STORE.dom.w,
            b = BG.STORE.dom.b,

            // vars
            toolbar,
            store,
            queryTime;

        /**
         * Обработчики
         */
        function bindEvents() {

            d.on('stat.update', function() {
                var typeStat,
                    params;

                // скрываем таблицу и график
                BG.tableStat.hide();
                BG.tableSum.hide();
                BG.chart.hide();

                // а выбраны ли какие-либо туры или объекты
                if (!BG.statistics.hasChecked()) return;

                // выбранный тип статистики
                typeStat = BG.tabsLine.getCurrentTab().data('value');
                // параметры из тулбара и бокового меню туров
                // которые требуются для запроса к API
                params = collectParams();

                $.when(query(typeStat, params))
                    .then(function(answer) {
                        var dataChart,
                            dataTable;

                        if (queryTime) clearTimeout(queryTime);
                        BG.statistics.loader.hide();

                        answer['error'] !== undefined
                            ? onError(answer['error'])
                            : onSuccess(typeStat, answer, params);
                    }, function(error) {

                        onError();
                    });
            });
        };

        /**
         * Сбор параметров
         * @return {object}
         */
        function collectParams() {
            var result = {},
                category;

            // параметры из тулбара
            toolbar = BG.toolbar.getState();
            if (toolbar.group) result.group = toolbar.group;
            if (toolbar.date_start) result.date_start = toolbar.date_start;
            if (toolbar.date_end) result.date_end = toolbar.date_end;
            if (toolbar.iframe) result.iframe = toolbar.iframe;

            // параметры из менюшки объектов/туров
            category = BG.categoryList.getChecked('as_string');
            if (category.estates_id) result.estates_id = category.estates_id;
            if (category.tours_id) result.tours_id = category.tours_id;

            return result;
        };

        /**
         * Запрос на получение данных
         * @return {Promise}
         */
        function query(type, params) {
            return $.ajax({
                    url: endpoint + type,
                    type: 'get',
                    dataType: 'json',
                    data: params,
                    beforeSend: beforeSend
                });
        };

        function beforeSend() {

            // если запрос не выполнится быстрее 100мс, то покажем лоадер
            // чтобы при быстрых запросах не было мелькания
            queryTime = setTimeout(BG.statistics.loader.show, 100);
        };

        function onSuccess(typeStat, answer, params) {

            // закешируем данные
            store = answer;

            answerIsNotEmpty(typeStat, answer, function() {

                // рендерим данные в таблицу и график

                // добавляем остальные параметры из тулбара,
                // которые для запроса были не нужны и поэтому откинуты
                $.extend(params, toolbar);

                // сначала рендерим таблицу с общими показателями
                BG.tableSum.show();
                BG.tableSum.update(typeStat, answer, params);

                // затем уже график и основную таблицу
                BG.tableStat.show();
                BG.tableStat.update(typeStat, answer, params);
                BG.chart.show();
                BG.chart.update(typeStat, answer, params);
            });
        };

        function onError(text) {

            BG.statistics.message(BG.CONST.STAT.MESSAGES.ERROR_DEFAULT, 'danger', {table: true, chart: true});
            if (text) console.warn(text);
        };

        // проверка на наличие данных
        function answerIsNotEmpty(typeStat, answer, func) {
            if (BG.parser.isEmpty[typeStat](answer)) {
                BG.statistics.message(BG.CONST.STAT.MESSAGES.DATA_EMPTY, 'info', {table: true, chart: true});
                return;
            } else {
                return func();
            }
        };

        /**
         * Публичные методы
         */
        common.init = function() {

            bindEvents();
        };

        /**
         * Возвращает ответ от API в случае наличия данных.
         * В противном случае выводит сообщение от отсутствии данных за выбранный период.
         * @return {object or undefined}
         */
        common.getStore = function() {
            return answerIsNotEmpty(BG.statistics.getType(), store, function() {
                return store;
            });
        };

        return common;
    })();

    BG.queryStat.init();
});