'use strict';

$(function() {

    /**
     * Модуль табличного вывода статистики
     */
    BG.statistics = (function() {
        var common = {},

            // const
            BC = 'statistics',

            // vars
            typeStat,

            // dom
            d = BG.STORE.dom.d,
            message,
            loader,
            parent;

        function prepareDOM() {

            message = $('.' + BC + '__message', parent);
            loader= $('.' + BC + '__loader', parent);
        };

        /**
         * Инициализация загрузки статистики
         */
        function start() {

            setTimeout(function() {

                // обновим состояние тулбара — необходимо актуализировать доступные типы графиков
                BG.toolbar.update();

                // запросим данные
                d.trigger('stat.update');
            }, 0);
        };

        /**
         * Вывод сообщения
         * @param {string} text Текст сообщения
         * @param {string} category Тип сообщения (success, info, warning, danger)
         */
        function messageCreate(text, category) {

            message.show().html(
                    BG.tmpl.other['tmpl__alert']({
                        category: category,
                        text: text
                    })
                );
        };

        /**
         * Удаление сообщения
         */
        function messageDestroy() {

            message.html('').hide();
        };

        /**
         * Инициализация модуля
         */
        common.init = function() {

            parent = $('.' + BC);
            if (!parent.length) return;

            prepareDOM();

            // кешируем глобальные параметры
            typeStat = parent.data('type');
            // задаем локаль
            moment.locale(BG.CONST.LANG);

            // запрашиваем данные
            start();
        };

        /**
         * Проверка на наличие выбранных туров или объектов
         * @return {boolean}
         */
        common.hasChecked = function() {
            var result = BG.categoryList.hasChecked();

            result
                ? messageDestroy()
                : messageCreate(BG.CONST.STAT.MESSAGES.PARAMS_EMPTY, 'info');

            return result;
        };

        /**
         * Вывод сообщения
         * @param {string} text Текст сообщения
         * @param {string} category Тип сообщения (success, info, warning, danger)
         * @param {object} hidden Объект с полями table и chart, определяющими скрывать ли одноименные блоки
         * @param {object} hidden
         */
        common.message = function(text, type, hidden) {
            var type = type || 'info',
                message;

            if (hidden) {
                if (hidden['table']) {
                    BG.tableStat.hide();
                    BG.tableSum.hide();
                }
                if (hidden['chart']) BG.chart.hide();
            }

            _.isArray(text)
                ? message = text.join('<br>')
                : message = text;

            messageCreate(message, type);
        };

        common.getType = function() {
            return typeStat;
        };

        common.loader = {
            show: function() {
                loader.show();
            },
            hide: function() {
                loader.hide();
            }
        };

        return common;
    })();

    BG.statistics.init();
});