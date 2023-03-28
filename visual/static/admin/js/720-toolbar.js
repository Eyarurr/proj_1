'use strict';

$(function() {

    /*
     * Модуль построения графиков
     */

    BG.toolbar = (function() {
        var person = {},
            common = {},

            // const
            BC = 'toolbar',
            START_STAT = '2015-01-01',

            // dom
            d = BG.STORE.dom.d,
            w = BG.STORE.dom.w,
            b = BG.STORE.dom.b,

            parent = $('.' + BC),
            form,
            inputRange,
            inputDate,
            datepicker,
            datepickerValue,
            datepickerStart,
            datepickerEnd,
            groupWide,
            groupRadio,
            groupSmall,
            groupSelect,
            type,
            iframe,

            // vars
            dateStartDefault,
            dateEndDefault,
            groupValue,
            groupList,
            typeStat,
            state = {},
            store = {};

        /**
         * Кеширование DOM-элементов
         * @return {void}
         */
        person.prepareDOM = function() {

            form = $('.' + BC + '__form', parent);

            // детализация
            groupWide = $('.' + BC + '__group', parent);
            groupRadio = $('input', groupWide);
            groupSmall = $('.' + BC + '__group-xs', parent);
            groupSelect = $('select', groupSmall);

            // выбора диапазона дат
            inputRange = $('.' + BC + '__period', parent);
            inputDate = $('.' + BC + '__date', parent);
            datepicker = $('.daterangepicker__container', inputRange.length ? inputRange : inputDate);
            datepickerValue = $('.daterangepicker__value', datepicker);
            datepickerStart = $('.daterangepicker__start', datepicker);
            datepickerEnd = $('.daterangepicker__end', datepicker);

            // тип графика
            type = $('.' + BC + '__type', parent);

            // доп. параметры
            iframe = $('.' + BC + '__iframe', parent);
        };

        /**
         * Навешивание обработчиков для обновления данных
         * или перестраивания графика
         * @return {void}
         */
        person.bindEvents = function() {

            // детализация
            groupWide.on('updated', function(event, value) {

                // обновим селект
                groupSelect.val(value);

                // сохраним новое значение в глобальном скоупе
                groupValue = value;

                person.datepicker();

                // запрашиваем новые данные
                d.trigger('stat.update');
                // сохраняем актуальное состояние в sessionStorage
                common.save();
            });

            groupSelect.on('change', function() {
                var value = $(this).val();

                // обновим радио группу
                groupWide.btnGroupRadio({active: value});

                // сохраним новое значение в глобальном скоупе
                groupValue = value;

                person.datepicker();

                // запрашиваем новые данные
                d.trigger('stat.update');
                // сохраняем актуальное состояние в sessionStorage
                common.save();
            });

            // // дата
            // datepickerStart.on('change', function(e) {

            //     // запрашиваем новые данные
            //     d.trigger('stat.update');
            //     // сохраняем актуальное состояние в sessionStorage
            //     common.save();
            // });

            // тип графика
            type.on('updated', function(event, value) {

                // парсим по-новой имеющиеся данные и строим график
                d.trigger('chart.update', value);

                // сохраняем актуальное состояние в sessionStorage
                common.save();
            });

            d.on('bg.resize', function(e, resp) {

                // обновляем вид контрола периода
                person.groupToggle(resp);
            });
        };

        /**
         * Переключение видимости выбора детализации в зависимости от разрешения
         * на широких экранах — радио-группа, на узких — селект
         */
        person.groupToggle = function(resp) {

            resp === 'xxs'
                ? person.groupToSmall()
                : person.groupToLarge();
        };

        /**
         * Детализация для широких экранов
         */
        person.groupToLarge = function() {

            groupSelect.prop('disabled', true);
            groupSmall.hide();

            groupRadio.prop('disabled', false);
            groupWide.show();
        };

        /**
         * Детализация для узких экранов
         */
        person.groupToSmall = function() {

            groupSelect.prop('disabled', false);
            groupSmall.show();

            groupRadio.prop('disabled', true);
            groupWide.hide();
        };

        person.datepicker = function() {
            var startDate,
                endDate,
                optionsCommon,
                options;

            if (!datepicker.length) return;

            inputRange.length
                ? datepickerRangeDate()
                : datepickerSingleDate();
        };

        /**
         * Возвращает тип статистики в единственном числе
         */
        function getSingularType(type) {
            return type.split('s')[0];
        };

        /**
         * Запись интервала дат для календаря
         * @return {void}
         */
        function setDatesRange(start, end, isInit) {
            var str,
                isEqual,
                isEmpty,
                formatUser,
                formatApi;

            // интервал не выбран
            isEmpty = !start;

            if (isEmpty) {

                datepickerValue.html(BG.CONST.STAT.FIELDS['not_selected']);
                datepickerStart.val('');
                datepickerEnd.val('');
            } else {

                // даты равны?
                isEqual = end.diff(start, 'days') === 0;

                formatUser = getFormatRangeDateUser(groupValue);
                formatApi = getFormatRangeDateAPI(groupValue);

                // отображаемый период
                isEqual
                    ? str = start.format(formatUser)
                    : str = start.format(formatUser) + ' — ' + end.format(formatUser);
                datepickerValue.html(str);

                // значения дат для API
                datepickerStart.val(start.format(formatApi));
                datepickerEnd.val(end.format(formatApi));
                // datepickerEnd.val(isEqual ? '' : end.format('YYYY-MM-DD'))
            }

            if (!isInit) {
                // запрашиваем новые данные
                d.trigger('stat.update');
                // сохраняем актуальное состояние в sessionStorage
                common.save();
            }
        };

        function datepickerRangeDate() {
            var optionsCommon,
                optionsMore,
                datapickerCurrent,
                dateStartStore,
                dateEndStore,
                dd,
                options;

            // удаляем старый календарь и события для него
            datapickerCurrent = datepicker.data('daterangepicker');
            if (datapickerCurrent) {
                datepicker.off('apply.daterangepicker showCalendar.daterangepicker hideCalendar.daterangepicker hide.daterangepicker');
                datapickerCurrent.remove();
            }

            // даты из sessionStorage
            dateStartStore = person.getDateStartFromStore();
            dateEndStore = person.getDateEndFromStore();

            // опции в зависимости от типа детализации
            optionsMore = getOptionsRangeDate(groupValue);
            if (!optionsMore.startDate) {
                // если дата не задана, значит период выбирать не требуется
                // очистим инпуты и скроем блок
                setDatesRange(null, null, true);
                inputRange.hide();
                return;
            } else {
                inputRange.show();
            }

            // дефолтные опции для всех типов детализации
            optionsCommon = {
                locale: {
                    customRangeLabel: BG.CONST.STAT.FIELDS['custom_range']
                },
                alwaysShowCalendars: false,
                showCustomRangeLabel: false,
                autoApply: true,
                opens: 'center',
                maxDate: moment(),
                minDate: moment(START_STAT),
            };
            options = $.extend({}, optionsCommon, optionsMore);

            // инициализируем
            datepicker.daterangepicker(options, setDatesRange);
            // вешаем обработчики
            datepicker
                .on('apply.daterangepicker', function(ev, picker) {

                    $('.b-overlay').remove();
                    picker.container.removeClass('separately');
                    BG.page && BG.page.scroll.on();

                    // запрашиваем новые данные
                    d.trigger('stat.update');
                    // сохраняем актуальное состояние в sessionStorage
                    common.save();
                })
                .on('showCalendar.daterangepicker', function(ev, picker) {

                    if ($('.b-overlay').length) return;
                    fitCalendar(picker);
                })
                .on('hideCalendar.daterangepicker', function(ev, picker) {

                    $('.b-overlay').remove();
                    picker.container.removeClass('separately');
                    BG.page && BG.page.scroll.on();
                })
                .on('show.daterangepicker', function(ev, picker) {
                    fitCalendar(picker);
                })
                .on('hide.daterangepicker', function(ev, picker) {

                    $('.b-overlay').remove();
                    picker.container.removeClass('separately');
                    BG.page && BG.page.scroll.on();
                });


            // ссылка на объект календаря
            datapickerCurrent = datepicker.data('daterangepicker');

            // либо из sessionStorage, либо дефолтные для выбранной детализации
            dateStartStore = dateStartStore || optionsMore.startDate;
            dateEndStore = dateEndStore || optionsMore.endDate;

            // пишем начальные значения
            datapickerCurrent.setStartDate(dateStartStore);
            datapickerCurrent.setEndDate(dateEndStore);
            setDatesRange(dateStartStore, dateEndStore, true);
        };

        function fitCalendar(picker) {
            var notFit,
                isDisplay;

            notFit = picker.container.offset().left + picker.container.outerWidth() > $(window).width();
            isDisplay = picker.container.css('display') === 'block';

            if (notFit) {
                picker.container.addClass('separately');
            }
            if (isDisplay && notFit) {
                if ($('.b-overlay').length === 0) $('body').append($('<div class="b-overlay"></div>'));
                BG.page.scroll.off();
            }
        };

        /*
         * Возвращает объект дополнительных опций, зависящих от выбранной детализации
         * @return {string}
         */
        function getOptionsRangeDate(detail) {
            var result = {},
                startDate,
                endDate;

            // быстрая навигация
            result.ranges = {};

            switch (detail) {
                case 'hours':

                    // по умолчанию показываем последние сутки
                    startDate = moment().subtract(1, 'days');
                    endDate = moment();

                    result.ranges[BG.CONST.STAT.FIELDS['today']] = [moment(), moment()];
                    result.ranges[BG.CONST.STAT.FIELDS['yesterday']] = [moment().subtract(1, 'days'), moment().subtract(1, 'days')];
                    result.ranges[BG.CONST.STAT.FIELDS['last_two_days']] = [startDate, endDate];
                    break;

                case 'days':

                    // по умолчанию показываем последние 30 дней
                    startDate = moment().subtract(1, 'month').add(1, 'days');
                    endDate = moment();

                    result.ranges[BG.CONST.STAT.FIELDS['week']] = [moment().subtract(6, 'days'), moment()];
                    result.ranges[BG.CONST.STAT.FIELDS['month']] = [startDate, endDate];
                    result.ranges[BG.CONST.STAT.FIELDS['quarter']] = [moment().subtract(3, 'months').add(1, 'days'), moment()];
                    result.ranges[BG.CONST.STAT.FIELDS['year']] = [moment().subtract(1, 'years').add(1, 'days'), moment()];

                    result.showCustomRangeLabel = true;
                    break;

                case 'months':

                    // по умолчанию показываем последние 12 месяцев
                    startDate = moment().add(1, 'month').subtract(2, 'years');
                    endDate = moment();

                    result.ranges[BG.CONST.STAT.FIELDS['year']] = [moment().add(1, 'month').subtract(1, 'years'), moment()];
                    result.ranges[BG.CONST.STAT.FIELDS['this_year']] = [moment().startOf('year'), moment().startOf('month')];
                    result.ranges[BG.CONST.STAT.FIELDS['last_year']] = [moment().subtract(1, 'years').startOf('year'), moment().subtract(1, 'years').endOf('year')];
                    result.ranges[BG.CONST.STAT.FIELDS['last_3_years']] = [startDate, endDate];
                    break;

                case 'years':

                    // по умолчанию показываем всё
                    startDate = null;
                    endDate = null;
                    break;

                default:
            };

            result.startDate = startDate;
            result.endDate = endDate;

            return result;
        };

        function getFormatRangeDateAPI(detail) {
            return 'YYYY-MM-DD';
        };

        /*
         * Возвращает формат, в котором дата показывается пользователю
         * @return {string}
         */
        function getFormatRangeDateUser(detail) {
            var result;

            switch (detail) {

                case 'months':
                    result = 'MMM YYYY';
                    break;

                case 'years':
                    result = 'YYYY';
                    break;

                case 'hours':
                case 'days':
                default:
                    result = 'D MMM YYYY';
                    break;
            };

            return result;
        };

        /**
         * Инициализация датапикета с одиночной датой
         */
        function datepickerSingleDate() {
            var optionsCommon,
                datapickerCurrent,
                dd,
                dateStartStore,
                dateResult,
                options;

            // удаляем старый календарь и события для него
            datapickerCurrent = datepickerEnd.data('DateTimePicker');
            if (datapickerCurrent) {
                datepickerEnd.off('dp.change');
                datepickerValue.off(BG.clickEvent);
                datapickerCurrent.destroy();
            }

            // значение даты из sessionStorage
            dateStartStore = person.getDateStartFromStore();
            // дефолтное значение, если нет сохраненного
            dd = moment().startOf(getSingularType(groupValue));

            dateResult = dateStartStore || dd;

            // дефолтные опции для всех типов детализации
            //
            optionsCommon = {
                defaultDate: dateResult,
                date: dateResult,
                maxDate: moment(),
                minDate: moment(START_STAT),
                widgetParent: datepicker,
                format: getFormatSingleDateAPI(groupValue),
                // useCurrent: true
            };

            // добавляем опции в зависимости от выбранной детализации
            options = $.extend({}, optionsCommon, getOptionsSingleDate(groupValue));

            datepickerEnd
                .datetimepicker(options)
                .on('dp.change', setDateSingle);

            // открытие датапикера при клике на текстовую подпись
            datepickerValue.on(BG.clickEvent, function() {
                datepickerEnd.data('DateTimePicker').toggle();
            });

            // пишем начальные значения
            setDateSingle({date: dateResult}, true);
        };

        /**
         * Запись конкретной даты для календаря
         * @return {void}
         */
        function setDateSingle(e, isInit) {

            // показывается пользователю
            datepickerValue.text(e.date.format(getFormatSingleDateUser(groupValue)));
            // отдается в API
            datepickerStart.val(e.date.format('YYYY-MM-DD'));

            if (!isInit) {
                // запрашиваем новые данные
                d.trigger('stat.update');
                // сохраняем актуальное состояние в sessionStorage
                common.save();
            }
        };

        /*
         * Возвращает объект дополнительных опций, зависящих от выбранной детализации
         * @return {string}
         */
        function getOptionsSingleDate(detail) {
            var result = {};

            switch (detail) {
                case 'days':
                    result.viewMode = 'days';
                    break;

                case 'months':
                    result.viewMode = 'months';
                    break;

                case 'years':
                    result.viewMode = 'years';
                    break;

                default:
            };

            return result;
        };

        /*
         * Возвращает формат, в котором дата отсылается в запросах к API
         * @return {string}
         */
        function getFormatSingleDateAPI(detail) {
            var result;

            switch (detail) {

                case 'months':
                    result = 'YYYY-MM';
                    break;

                case 'years':
                    result = 'YYYY';
                    break;

                case 'days':
                default:
                    result = 'YYYY-MM-DD';
                    break;
            };

            return result;
        };

        /*
         * Возвращает формат, в котором дата показывается пользователю
         * для одиночного датапикера
         * @return {string}
         */
        function getFormatSingleDateUser(detail) {
            var result;

            switch (detail) {

                case 'months':
                    result = 'MMMM YYYY';
                    break;

                case 'years':
                    result = 'YYYY';
                    break;

                case 'days':
                default:
                    result = 'D MMM YYYY';
                    break;
            };

            return result;
        };

        // кешируем глобальные параметры
        function paramsInit() {

            // тип статистики
            typeStat = parent.data('type');

            // дефолтное значение детализации
            groupValue = groupWide.find('.active input').val();
            // доступные значения детализации
            groupList = groupWide.find('input').map(function(index, elem) {
                return $(this).val();
            }).toArray();
        };

        /**
         * Чтение текущих параметров тулбара
         */
        function readToolbarStorage() {
            var result = sessionStorage.getItem('toolbar');

            try {
                result = JSON.parse(result) || {};
            } catch (e) {
                result = {};
            }

            return result;
        };

        /**
         * Инициализация модуля
         */
        common.init = function() {

            if (!parent.length) return;

            person.prepareDOM();
            person.bindEvents();

            // кешируем глобальные параметры
            paramsInit();
            // восстанавливаем состояние из sessionStorage
            common.restore();

            // инициализируем календарь
            person.datepicker();
        };

        /**
         * Возвращает состояние фильтра — все параметры
         * @return {object}
         */
        common.getState = function() {
            var result = {};

            if (!parent.length) return result;

            // собираем в массив пар ключ/значение
            result = form.serialize().split('&').map(function(el, index) {
                return el.split('=');
            });

            // преобразуем в объект
            result = _.object(result);

            // костыль, потом выпилить
            if (typeStat !== 'traffic' && result['date_end']) delete result.date_end;

            return result;
        };

        /**
         * Показать
         * @return {void}
         */
        common.show = function() {
            parent.show();
        };

        /**
         * Скрыть
         * @return {void}
         */
        common.hide = function() {
            parent.hide();
        };

        /**
         * Актуализируем состояние тулбара в зависимости
         * от выбранного количества туров и объектов и типа статистики
         */
        common.update = function() {
            var count = BG.categoryList.getCount(),
                typeStat = BG.statistics.getType();

            switch (typeStat) {
                case 'traffic':

                    break;

                case 'geo':
                case 'time':
                case 'sources':
                    if (count > 1) {
                        // принудительно выбираем горизонтальный бар и скрываем
                        type.btnGroupRadio({active: 'column'}).hide();
                    } else {
                        // если тур/объект один даем возможность выбрать среди pie/column
                        type.show();
                    }

                    if (typeStat === 'time') {
                        count > 1
                            ? parent.addClass('hidden')
                            : parent.removeClass('hidden');
                    }
                    break;

                default:
            }
        };

        /**
         * Сохранение состояния тулбара: выбранный период
         * @return {void}
         */
        common.save = function() {
            var curState,
                curGroup;

            if (!Modernizr.sessionstorage) return;

            // текущее актуальное состояние
            state = common.getState();
            curGroup = state.group;

            // состояние из sessionStorage
            curState = readToolbarStorage();

            if (curState[typeStat] === undefined) curState[typeStat] = {};

            // мержим
            curGroup
                ? curState[typeStat][curGroup] = $.extend({}, curState[typeStat][curGroup], state)
                : curState[typeStat] = $.extend({}, curState[typeStat], state);

            // детализация будет единой на все типы статистики
            if (state.group) store = $.extend(curState, {group: state.group});

            sessionStorage.setItem('toolbar', JSON.stringify(store));
        };

        /**
         * Восстановление состояния тулбара (пока что только период)
         */
        common.restore = function() {
            var curItem;

            if (!Modernizr.sessionstorage) return;

            store = readToolbarStorage();

            // значение восстанавливаем, если есть такое значение в списке доступных
            // ведь hours в географии и источниках отсутствует
            if (store['group'] && groupList.indexOf(store['group']) >= 0) {
                // для узких экранов селект
                groupSelect.val(store['group']);
                // для широких экранов радио-группа
                groupWide.btnGroupRadio({active: store['group']});
                // обновим значение в глобальном scope
                groupValue = store['group'];
            }

            // сохраненная статистика для текущего типа
            curItem = store[typeStat] && store[typeStat][groupValue];

            // тип графика
            if (curItem && curItem['type']) {
                type.btnGroupRadio({active: curItem['type']});
            }

            // даты восстанавливаются на этапе инициализации датапикетов
        };

        person.getDateStartFromStore = function() {
            var result;
            result = store && store[typeStat] && store[typeStat][groupValue] && store[typeStat][groupValue].date_start;
            if (result) result = moment(result);
            return result;
        };
        person.getDateEndFromStore = function() {
            var result;
            result = store && store[typeStat] && store[typeStat][groupValue] && store[typeStat][groupValue].date_end;
            if (result) result = moment(result);
            return result;
        };

        return common;
    })();

    BG.toolbar.init();
});