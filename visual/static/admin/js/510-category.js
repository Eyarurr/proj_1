'use strict';

$(function() {

    BG.categoryList = (function() {
        var person = {},
            common = {},

            // const
            BC = 'b-category-list',
            PADD = 20,
            HEAD_MARGIN_BOTTOM = 60,

            // dom
            d = BG.STORE.dom.d,
            w = BG.STORE.dom.w,
            block = $('.' + BC),
            blockList,
            form,
            content,
            parent,
            footer = $('.footer'),

            // vars
            store,
            resp = '',
            scrollFlag = false,
            isCheck = false;

        person.prepareDOM = function() {

            // ищем родителя менюшки
            parent = block.parent();

            blockList = $('.' + BC + '__ul', block);
            form = $('.' + BC + '__form', block);
        };

        // toggle list categories on list page portfolio
        person.toggle = function(param) {
            var all;

            all = block.find('.' + BC + '__all');

            all.on(BG.clickEvent, function(e) {
                var self = $(this);
                e.preventDefault();

                block.toggleClass('b-category-list__open');
                blockList.slideToggle(400, function() { });
            });
        };

        // применяем скролл
        person.applyScroll = function(max) {
            // if (scrollFlag) return;

            // применяем nanoscroller
            block
                .addClass('nano')
                .nanoScroller({
                    preventPageScrolling: true,
                    // iOSNativeScrolling: true
                });

            // выставляем флаг
            scrollFlag = true;
        };

        // отменяем скролл
        person.destroyScroll = function() {
            if (!scrollFlag) return;

            // отменяем плагин
            block.nanoScroller({ destroy: true });
            block.removeClass('nano');

            // сбрасываем флаг
            scrollFlag = false;
        };

        // задаем высоту меню
        person.setMenuHeight = function() {
            var max,
                maxWindow;

            // высота левой колонки
            max = footer.offset().top - parent.offset().top;

            // высота окна
            maxWindow = w.height();

            if (max > maxWindow) max = maxWindow;
            // высота шапки - отступ от шапки до меню - отступ снизу до меню
            max = max - BG.header.getHeight() - (Math.max(HEAD_MARGIN_BOTTOM - w.scrollTop(), PADD)) - PADD;

            // если высота контента больше высоты контейнера
            if (blockList.height() >= max) {

                block.height(max);
                person.applyScroll(max);

            } else {

                block.css({
                    'height': 'auto'
                });
                person.destroyScroll();

            }
        };

        // задаем высоту родителю
        person.setParentHeight = function() {
            var tmpCss,
                tmpClass,
                parentHeight,
                wW = w.height();

            parentHeight = blockList.height();

            // максимальная высота - высота окна
            if (parentHeight > wW) parentHeight = wW;

            // выставляем высоту родителя
            parent.height(parentHeight);
        };

        // позиционируем меню
        person.setMenuPosition = function(pos) {
            var scroll = w.scrollTop() + BG.header.getHeight(),
                parentWidth,
                parentHeight,
                footerTop = footer.offset().top,
                delta;

            if (scroll + PADD > pos) {
                // размеры родителя
                parentWidth = parent.width();

                // делаем менюшку плавающей
                block.addClass('b-category-list--fixed').css({
                    width: parentWidth
                });

                delta = scroll + block.height() + 2 * PADD;

                if (delta > footerTop) {
                    block.css({
                        'marginTop': footerTop - delta + PADD
                    });
                } else {
                    block.css({
                        'marginTop': PADD
                    });
                }
            } else {
                block.removeClass('b-category-list--fixed').css({
                    'width': 'auto',
                    'marginTop': 0
                });
            }
        };

        // плавающее меню
        person.bindStickEvents = function() {
            var blockOffsetTop;

            if (!block.hasClass(BC + '--stick')) return;

            // определеяем позицию top меню
            blockOffsetTop = block.offset().top;

            w.on('resize', function() {
                var resp = BG.visual.currentResp();

                if ((resp === 'xs') || (resp === 'xxs')) {

                    // отменяем скролл
                    person.destroyScroll();

                    // сброс
                    block.removeClass('b-category-list--fixed').removeAttr('style');
                    parent.removeAttr('style');

                } else {
                    blockOffsetTop = parent.offset().top;

                    // выставляем размеры родителя
                    person.setParentHeight();

                    // выставляем высоту меню
                    person.setMenuHeight();
                }
            });

            w.on('load folder.create', function() {
                var resp = BG.visual.currentResp();

                if ((resp === 'xs') || (resp === 'xxs')) {

                } else {
                    // выставляем размеры родителя
                    person.setParentHeight();

                    // выставляем высоту меню
                    person.setMenuHeight();

                    // позиционируем меню
                    person.setMenuPosition(blockOffsetTop);
                }
            });

            w.on('scroll', function(e) {
                var resp = BG.visual.currentResp();

                if ((resp === 'xs') || (resp === 'xxs')) {

                } else {

                    // выставляем размеры родителя
                    person.setParentHeight();

                    // обновляем высоту меню
                    person.setMenuHeight();

                    // позиционируем меню
                    person.setMenuPosition(blockOffsetTop);
                }
            });
        };

        /**
         * Применяем функционал выбора пунктов меню/подменю посредством чекбоксов
         * @return {void}
         */
        person.bindCheckEvents = function() {

            isCheck = block.hasClass(BC + '--checks');

            if (!isCheck) return;

            // // первоначальное состояние подменю
            // $('.' + BC + '__group', block).each(function(index, el) {
            //     var self = $(this),
            //         active = $('.' + BC + '__item--active', self);

            //     if (!active.length) self.hide();
            // });

            // выделение
            block.on(BG.clickEvent, 'input[type="checkbox"]', function(e) {
                var self = $(this),
                    name = self.prop('name'),
                    value = self.prop('value'),
                    item = self.closest('.' + BC + '__item'),
                    i;

                if (self.prop('checked')) {

                    storeAdd(name, value);
                    item.addClass(BC + '__item--active');
                } else {

                    storeRemove(name, value);
                    item.removeClass(BC + '__item--active');
                }

                handleChange();
            });

            // сворачивание/разворачивание вложенных уровней
            block.on(BG.clickEvent, '.' + BC + '__a', function(e) {
                var self = $(this),
                    item = self.parent(),
                    next = item.next('.' + BC + '__group');

                // вместо перехода по ссылке
                e.preventDefault();

                if (next.length) {

                    // будем скрывать или показывать подменю
                    next.toggle();

                    // обновим высоту левой колонки и меню
                    // а также сделаем переинициализацию nanoscroll
                    d.trigger('scroll');
                } else {

                    $('.' + BC + '__checkbox', item).trigger(BG.clickEvent);
                }
            });

            // переключение всех вложенных туров
            block.on(BG.clickEvent, '.' + BC + '__double', function(e) {
                var self = $(this),
                    parent = self.parent(),
                    childs = parent.next('.' + BC + '__group').children('.' + BC + '__item'),
                    checks = $('.' + BC + '__checkbox', childs),
                    hasChecked = checks.filter(':checked').length > 0;

                checks.each(function(index, el) {
                    var ch = $(this),
                        item = ch.parent(),
                        name = ch.prop('name'),
                        value = ch.prop('value');

                    ch.prop('checked', !hasChecked);
                    if (hasChecked) {
                        storeRemove(name, value);
                        item.removeClass(BC + '__item--active');
                    } else {
                        storeAdd(name, value);
                        item.addClass(BC + '__item--active');
                    }
                });

                handleChange();
            });
        };

        /**
         * Обработчик изменения списка выбранных объектов/туров
         */
        function handleChange() {

            // пишем в табы get-параметры, включающие в себя список туров и объектов
            person.setGetParams();
            // обновим состояние тулбара — возможно необходимо изменение списка доступных типов графиков
            BG.toolbar.update();
            // и сохраним текущее состояние
            BG.toolbar.save();
            // изменились туры или объекты, а значит нужно запросить новые данные
            d.trigger('stat.update');
        };

        //
        person.setGetParams = function() {
            BG.tabsLine.setGetParams(common.getChecked('as_url'));
        };

        /**
         * Инициализация первоначального состояния выбранных пунктов
         * в формате {estates_id: [], tours_id: []}
         * @return {object}
         */
        function storeInit() {
            var pairs = [],
                result,
                state;

            // очищаем списки выбранных объектов/туров
            result = {
                estates_id: [],
                tours_id: []
            };

            state = form.serialize();

            if (state !== '') {

                state = state.split('&');
                state.forEach(function(el, index) {
                    pairs.push(el.split('='));
                });
                pairs.forEach(function(el, index) {
                    result[el[0]].push(el[1]);
                });
            }

            return result;
        };

        /**
         * Добавить объект/тур в хранилище
         */
        function storeAdd(name, value) {
            store[name].push(value);
        };

        /**
         * Удалить объект/тур из хранилища
         */
        function storeRemove(name, value) {
            var i = store[name].indexOf(value);
            if (i >= 0) store[name].splice(i, 1);
        };

        /**
         * Инциализация модуля
         */
        common.init = function() {

            if (!block.length) return;

            person.prepareDOM();

            // функционал выбора пунктов меню
            person.bindCheckEvents();

            // функционал сворачивания
            person.toggle();

            // фиксирование в видимой части экрана — плавающее меню
            person.bindStickEvents();

            // инициализация хранилища выбранных туров/объектов
            store = storeInit();
            // и запись выбранных значений в урлы табов
            person.setGetParams();
        };

        // возвращаем активный пункт меню
        common.getActive = function() {
            var cur = block.find('.' + BC + '__active a'),
                result;

            cur.length
                ? result = {
                        href: cur.eq(0).attr('href'),
                        text: cur.eq(0).text()
                    }
                : result = false;

            return result;
        };

        /**
         * Возвращает актуальное состояние выбранных пунктов меню
         * @param {string} type Тип, в котором необходимо вернуть список идентификаторов (as_string, as_array, as_url)
         * @return {object}
         */
        common.getChecked = function(type) {
            var result = $.extend({}, store),
                res;

            if (type === 'as_string' || type === 'as_url') {
                result.estates_id = result.estates_id.join(',');
                result.tours_id = result.tours_id.join(',');

                if (type === 'as_url') {
                    // склеиваем идентификаторы туров и объектов в строку get-параметров
                    result = (store.estates_id.length ? 'estates_id=' + result.estates_id + (store.tours_id.length ? '&' : '') : '') +
                             (store.tours_id.length ? 'tours_id=' + result.tours_id : '');
                }
            }

            return result;
        };

        /**
         * Возвращает общее количество выбранных элементов меню
         * по сути общее количество объектов и туров
         * @return {integer}
         */
        common.getCount = function() {
            return store.estates_id.length + store.tours_id.length;
        };

        /**
         * Возвращает есть ли выбранные элементы ?
         * @return {boolean}
         */
        common.hasChecked = function() {
            return store.estates_id.length + store.tours_id.length > 0;
        };

        /**
         * Возвращает название тура/объекта по идентификатору
         * @return {string}
         */
        common.getTitleById = function(type, id) {
            var name = type === 'tours' ? 'tours_id' : 'estates_id';
            return parent.find('input[type="checkbox"][name="' + name + '"][value="' + id +'"]').next().text();
        };

        return common;
    })();

    BG.categoryList.init();
});
