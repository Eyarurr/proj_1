'use strict';

$(function() {

    /**
     * Модуль построения графиков
     */

    BG.chart = (function() {
        var person = {},
            common = {},

            // const
            BC = 'chart',
            optionsHandle = {
                handleRendered: {
                    "event": "rendered",
                    "method": function(e) {
                        var len,
                            params = BG.toolbar.getState();

                        // задание отображаемого интервала
                        // только для посещаемости
                        if (params.group && BG.statistics.getType() === 'traffic') {
                            len = e.chart.dataProvider.length;
                            e.chart.zoomToIndexes(len - optionsZoom[params.group].start, len - optionsZoom[params.group].end);
                        }
                    }
                },
                handleInit: {
                    "event": "init",
                    "method": function(e) {
                        var categoryWidth,
                            base = 25,
                            chartHeight,
                            isStacked,
                            countGraphs,
                            countRows,
                            k;

                        // высоту регулируем только для перевёрнутых графиков
                        if (e.chart.rotate) {

                            // режим stack?
                            isStacked = e.chart.valueAxes[0].stackType === 'regular';
                            // количество колонок в одном блоке
                            countGraphs = isStacked ? 1 : e.chart.graphs.length;
                            // коэффициент увеличения ширины одного столбика
                            k = 1 + 1 / countGraphs;
                            // количество блоков
                            countRows = e.chart.dataProvider.length;

                            categoryWidth = Math.floor(base * k) * countGraphs;
                            chartHeight = categoryWidth * countRows + 100;

                            e.chart.div.style.height = chartHeight + 'px';
                        } else {

                            e.chart.div.style.removeProperty('height');
                        }
                    }
                }
            },

            // параметры в зависимости от типа графика
            graphType = {
                pie: {

                },
                column: {
                    "fillAlphas": 0.8
                },
                line: {
                    "bullet": "round",
                    "bulletBorderAlpha": 1,
                    "bulletColor": "#FFFFFF",
                    "bulletSize": 7,
                    "hideBulletsCount": 50,
                    "lineThickness": 2,
                    "useLineColorForBulletBorder": true
                },
            },
            chartType = {
                pie: {
                    "type": "pie",
                    "innerRadius": "40%",
                    "valueField": "visits",
                    "startDuration": 0,
                    "chartCursor": {
                        "enabled": false
                    },
                    "legend": {
                        "enabled": false
                    }
                },
                column: {
                    "type": "serial",
                    "chartCursor": {
                        // "categoryBalloonEnabled": false,
                        // "cursorAlpha": 0,
                    },
                    "mouseWheelScrollEnabled": false,
                    "mouseWheelZoomEnabled": false
                },
                line: {
                    "type": "serial",
                    "chartScrollbar": {
                        "oppositeAxis": false,
                        "offset": 40,
                        "autoGridCount": true,
                        "color": "#AAAAAA"
                    },
                    "mouseWheelScrollEnabled": false,
                    "mouseWheelZoomEnabled": false
                },
            },
            // параметры в зависимости от типа группировки
            chartGroup = {
                hours: {
                    "chartCursor": {
                        "categoryBalloonDateFormat": "JJ:NN, D MMM"
                    },
                    "categoryAxis": {
                        "minPeriod": "hh"
                    }
                },
                days: {
                    "chartCursor": {
                        "categoryBalloonDateFormat": "D MMM"
                    },
                    "categoryAxis": {
                        "minPeriod": "DD"
                    }
                },
                months: {
                    "chartCursor": {
                        "categoryBalloonDateFormat": "MMMM YYYY"
                    },
                    "categoryAxis": {
                        "minPeriod": "MM"
                    }
                },
                years: {
                    "chartCursor": {
                        "categoryBalloonDateFormat": "YYYY"
                    },
                    "categoryAxis": {
                        "minPeriod": "YYYY"
                    }
                }
            },
            statType = {
                traffic: {
                    "dataDateFormat": "YYYY-MM-DD JJ:NN:SS",
                    "categoryField": "date",
                    "categoryAxis": {
                        "parseDates": true,
                    },
                    "chartScrollbar": {
                        "oppositeAxis": false,
                        "offset": 40,
                        "autoGridCount": true,
                        "color": "#AAAAAA"
                    },
                },
                geo: {
                    // "rotate": true,
                    "categoryField": "city_country",
                    "titleField": "city_country",
                    "chartCursor": {
                        "zoomable": false
                    },
                    "categoryAxis": {
                        "gridPosition": "start"
                    }
                    // "categoryAxis": {
                    //     "autoGridCount": false,          // показываем все значения
                    // }
                },
                time: {
                    "categoryField": "time",
                    "titleField": "time",
                    "categoryAxis": {
                        "gridPosition": "start"
                    }
                    // "responsive": {
                    //     "rules": [
                    //         {
                    //             "maxWidth": 500,
                    //             "overrides": {
                    //                 "categoryAxis": {
                    //                     "labelRotation": 30
                    //                 }
                    //             }
                    //         }
                    //     ]
                    // },
                },
                sources: {
                    // "rotate": true,
                    "categoryField": "referer_host",
                    "titleField": "referer_host",
                    "chartCursor": {
                        "zoomable": false
                    },
                    "categoryAxis": {
                        "gridPosition": "start"
                    }
                    // "categoryAxis": {
                    //     "autoGridCount": false,          // показываем все значения
                    //     "labelFrequency": 1
                    // }
                }
            },
            // начальные интервалы отображения
            optionsZoom = {
                hours: {
                    start: 24,
                    end: 1
                },
                days: {
                    start: 30,
                    end: 1
                },
                months: {
                    start: 12,
                    end: 1
                },
                years: {
                    start: 10,
                    end: 1
                }
            },

            // dom
            d = BG.STORE.dom.d,
            w = BG.STORE.dom.w,
            b = BG.STORE.dom.b,

            parent = $('.' + BC),
            canvas,
            legend,
            download,

            painter,
            options,                // опции
            config,                 // конфиг
            type;                   // тип графика

        /**
         * Кеширование DOM-элементов
         * @return {void}
         */
        person.prepareDOM = function() {

            canvas = $('.' + BC + '__canvas');
            legend = $('.' + BC + '__legend');
            download = $('.' + BC + '__download');
        };

        /**
         * Обработчики для графика
         * @return {void}
         */
        person.bindEvents = function() {

            /**
             * Подписка на обновление графика, тригерится когда переключился тип графика
             * @param {Event} e Нативное событие
             * @param {string} typeChart
             */
            d.on('chart.update', function(e, typeChart) {

                common.update(typeChart);
            });
        };

        /**
         * Мержим кастомные опции с дефолтными для данного типа графика
         * @param {object} params Параметры тулбара
         * @return {void}
         */
        person.mergeOptions = function(params) {

            options = {};
            // параметры в зависимости от типа выбранной статистики: traffic, geo, time, sources
            options = $.extend(true, options, statType[BG.statistics.getType()]);
            // параметры в зависимости от выбранного типа графика: column, line, pie
            if (params.type) options = $.extend(true, options, chartType[params.type]);
            // параметры в зависимости от выбранной группировки: hours, days, months, years
            if (params.group) options = $.extend(true, options, chartGroup[params.group]);
        };

        /**
         * Формирование подписей к каждому набору данных
         * @param {string} typeChart Тип графика
         * @param {array} list Список идентификаторов данных (либо название поля, либо идентификаторы туров/объектов)
         */
        function generateGraphs(typeChart, list) {
            var result,
                item = {
                    type: typeChart,
                };

            item = $.extend(item, graphType[typeChart]);

            result = list.map(function(elem, index) {
                var newItem = $.extend({}, item);
                newItem.id = 'g' + index;
                newItem.valueField = elem;
                newItem.title = BG.parser.getHumanLabel(elem);
                return newItem;
            });

            return result;
        };

        /**
         * Формирование конфига
         * @param {string} params Тип графика
         * @param {object} parsedData Готовые данные
         */
        person.prepareConfig = function(params, parsedData) {
            var statType = BG.statistics.getType(),
                currResp = BG.visual.currentResp(),
                countCategories = BG.categoryList.getCount();

            config = {
                "language": BG.CONST.LANG,
                "theme": "light",
                "fontFamily": "Verdana, Tahoma, Helvetica Neue, Lucida Grande, sans-serif",
                "legend": {
                    "horizontalGap": 10,
                    "position": "top",
                    "align": "center",
                    "fontSize": 11,
                    "divId": "legend"               // легенду будем генерировать в отдельный див, чтобы жестко регулировать высоту самого графика
                },
                "responsive": {
                    "enabled": true
                },
                "chartCursor": {
                    "valueLineEnabled": false,
                    "valueLineBalloonEnabled": false,
                    // "pan": true,
                    "cursorPosition": "mouse",
                    "cursorAlpha": 1,
                    "cursorColor": "#cd3339"
                },
                "categoryAxis": {},
                "valueAxes": [{
                    "id": "v1",
                    "min": 0,                       // ось значений всегда с 0
                    "integersOnly": true,           // только целые числа
                    "includeAllValues": true        // фиксирует минимум и максимум при скроллировании графика
                }],
                "numberFormatter": {
                    "precision": -1,
                    "decimalSeparator": ".",
                    "thousandsSeparator": " "
                },
                // https://github.com/amcharts/export
                "export": {
                    "enabled": true,
                    "divId": "download",
                    "menu": [{
                        "class": "export-main",
                        "menu": [
                            {
                                "label": BG.CONST.STAT.MESSAGES.DOWNLOAD_AS,
                                "menu": ["PNG", "JPG", "PDF"]
                            },
                            {
                                "label": BG.CONST.STAT.MESSAGES.PRINT,
                                "format": "PRINT"
                            }
                        ]
                    }]
                },
                // "zoomOutOnDataUpdate": false,
                "dataProvider": parsedData.datasets.get(),
                "listeners": [optionsHandle.handleRendered, optionsHandle.handleInit]
            };

            // идентификаторы полей с названиями данных
            // типы column и line
            if (parsedData.graphs) config = $.extend(true, config, {"graphs": generateGraphs(params.type, parsedData.graphs)});

            config = $.extend(true, config, options);

            // костыли
            if (params.type === 'column' && countCategories === 1 && statType === 'sources') config.valueAxes[0].stackType = 'regular';

            // отключаем линию курсора
            if (params.type === 'column') config.chartCursor.cursorAlpha = 0;

            // везде кроме посещаемости отключаем балун текущего названия категории
            if (statType !== 'traffic') config.chartCursor.categoryBalloonEnabled = false;

            // поворачиваем график только в географии и источниках
            if (params.type === 'column' && (statType === 'geo' || statType === 'sources')) config.rotate = true;

            // для пирогов на малых разрешениях отключаем лейблы и включаем легенду
            if (params.type === 'pie' && (currResp === 'sm' || currResp === 'xs' || currResp === 'xxs')) {
                config.legend.enabled = true;
                config.labelsEnabled = false;
            }

            // для времени просмотра поворачиваем лейблы оси категорий при узких экранов
            if (statType === 'time' && (currResp === 'sm' || currResp === 'xs' || currResp === 'xxs')) {
                config.categoryAxis.labelRotation = 30;
            }

            // даем возможность сохранения графиков только для широких экранов
            if (currResp !== 'lg' && currResp !== 'md') config.export.enabled = false;

            // console.log('config', config, params);
        };

        /**
         * Отрисовка графика
         * @return {void}
         */
        person.draw = function(params) {
            painter = AmCharts.makeChart('chart', config);
        };

        /**
         * Инициализация
         */
        common.init = function() {

            if (!parent.length) return;

            // кешируем DOM и навешиваем обработчики
            person.prepareDOM();
            person.bindEvents();
        };

        /**
         * Рендерим переданные данные по заданному типу
         * остальные параметры узнаем из текущего состояния тулбара и сайдменю
         * @param {string} type Тип запроса: traffic, geo, time, sources ---
         * @param {object} data Данные
         * @param {object} params Параметры запроса
         */
        common.update = function(type, data, params) {
            var preparedData,
                params = params || BG.toolbar.getState(),
                typeStat = BG.statistics.getType(),
                store = BG.queryStat.getStore();

            if (painter) {
                painter.clear();
                legend.html('');
                download.html('');
            }

            // проверка на наличие данных
            if (!data && !store) return;

            // распарсиваем данные в соответствии с параметрами тулбара (типом графика и др.)
            preparedData = BG.parser.chart[typeStat](data || store, params);

            // обработка ошибок при подготовке данных
            if (preparedData['errors']) {
                BG.statistics.message(preparedData['errors'], 'info', {chart: true});
                return;
            }

            person.mergeOptions(params);
            person.prepareConfig(params, preparedData);
            person.draw(params);
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

    BG.chart.init();
});