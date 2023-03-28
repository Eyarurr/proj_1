'use strict';

// var BG = {};

/* touch event */
BG.isTouchDevice = Modernizr.touch;
// BG.clickEvent = BG.isTouchDevice ? 'touchend' : 'click';
BG.clickEvent = 'click';
BG.enterEvent = BG.isTouchDevice ? 'touchmove' : 'mouseenter';
BG.leaveEvent = BG.isTouchDevice ? 'touchend' : 'mouseleave';
BG.inputEvent = ('oninput' in document.createElement('INPUT')) ? 'input' : 'keyup';

// window.BG = BG;

_.templateSettings.variable = "rc";

// формат именования кастомных событий
// click.{{element}} - e
// keypress.{{key_name}} - w
// load.{{page}} - w

$(function() {

    BG.STORE = (function () {
        var person = {},
            common = {};

        var cacheDOM = [],
            cacheDATA = [];

        common.dom = {
            get: function(selector) {
                return cacheDOM[selector] || (cacheDOM[selector] = $(selector));
            },
            clear: function(selector) {
                selector == null ? cacheDOM = [] : cacheDOM[selector] = null;
            }
        };

        common.dom.d = $(document);
        common.dom.w = $(window);
        common.dom.b = $('body');

        common.data = {
            set: function(key, value) {
                cacheDATA[key] = value;
            },
            get: function(key) {
                return cacheDATA[key];
            },
            clear: function(key) {
                key == null ? cacheDATA = [] : cacheDATA[key] = null;
            }
        };

        return common;
    })();

    BG.STORE.data.set('isDesktop', bowser.mobile === undefined && bowser.tablet === undefined);

    BG.isMobile = {
        Android: (function() {
            return navigator.userAgent.match(/Android/i);
        })(),
        BlackBerry: (function() {
            return navigator.userAgent.match(/BlackBerry/i);
        })(),
        iOS: (function() {
            return navigator.userAgent.match(/iPhone|iPad|iPod/i);
        })(),
        Opera: (function() {
            return navigator.userAgent.match(/Opera Mini/i);
        })(),
        Windows: (function() {
            return navigator.userAgent.match(/IEMobile/i);
        })()
    };
    BG.isMobile.any = (function() {
        return (BG.isMobile.Android || BG.isMobile.BlackBerry || BG.isMobile.iOS || BG.isMobile.Opera || BG.isMobile.Windows);
    })();

    BG.CONST.RESP = {
        XXS: 480,
        XS: 768,
        SM: 992,
        MD: 1200
    };

    BG.CONST.RESP_NAMES = ['xxs', 'xs', 'sm', 'md', 'lg'];

    BG.CONST.PATTERN = {
        EMAIL: /^[-\w.]+@([A-z0-9][-A-z0-9]+\.)+[A-z]{2,4}$/
    };

    BG.CONST.KEY = {
        ESCAPE: 27,
        ENTER: 13
    };

    BG.CONST.SPLITTER = '_';

    BG.common = (function() {
        var person = {},
            common = {};

        // отбивка тысяч
        common.thousandSeparator = function(str) {
            var parts = (str + '').split('.'),
                main = parts[0],
                len = main.length,
                output = '',
                i = len - 1;

            while(i >= 0) {
                output = main.charAt(i) + output;
                if ((len - i) % 3 === 0 && i > 0) {
                    output = ' ' + output;
                }
                --i;
            }

            if (parts.length > 1) {
                output += "." + parts[1];
            }
            return output;
        };

        common.getDateFullFormat = function(date, local) {
            var fullDate = new Date(date);
            return fullDate.toLocaleDateString(local);
        };

        /**
         * Вычисление ширины скроллбара
         * @return {integer}
         */
        common.getScrollbarWidth = function() {
            var outer,
                inner,
                widthNoScroll,
                widthWithScroll;

            // создаем блок
            outer = document.createElement('div'),
            outer.style.visibility = 'hidden';
            outer.style.width = '100px';
            outer.style.msOverflowStyle = 'scrollbar';
            document.body.appendChild(outer);

            // и вычисляем его ширину
            widthNoScroll = outer.offsetWidth;
            outer.style.overflow = 'scroll';

            // кладем внутрь еще один блок
            inner = document.createElement('div');
            inner.style.width = '100%';
            outer.appendChild(inner);

            // вычисляем ширину внутреннего блока
            widthWithScroll = inner.offsetWidth;

            // подчищаем за собой
            outer.parentNode.removeChild(outer);

            // ширина скрола будет составлять разницу между найденными ширинами
            return widthNoScroll - widthWithScroll;
        };

        /**
         * Добавление динамического CSS
         */
        common.addCalcCSS = function() {
            var styles = [
                '.scroll-disable.is-desktop,',
                '.modal__open.is-desktop,',
                '.modal-open.is-desktop .b-header--fixed,',
                '.modal-open.is-desktop .b-header--behind,',
                '.modal__open.is-desktop .b-header--fixed,',
                '.modal__open.is-desktop .b-header--behind {',
                    'padding-right: ' + BG.STORE.data.get('scrollBar') + 'px;',
                '}'
            ].join('');

            var headCSS = $('<style type="text/css"></style>');
            headCSS.text(styles);

            BG.STORE.dom.get('head').append(headCSS);
        };

        /**
         * Конвертируем в HTTPS
         */
        common.http2https = function(str) {
            if (typeof str !== 'string') return '';
            return str.replace(/^http:\/\//i, 'https://');
        };

        /**
         * Копирование объекта
         * @return {object}
         */
        common.cloneDeep = function(data) {
            return JSON.parse(JSON.stringify(data));
        };

        return common;
    })();

    // сохраняем ширину скролла
    BG.STORE.data.set('scrollBar', BG.common.getScrollbarWidth());

    // добавляем динамический CSS
    BG.common.addCalcCSS();

    // кеширование js-шаблонов
    BG.tmpl = (function() {
        var person = {},
            common = {},
            modal = $('.template-modal'),
            modalBts = $('.template-bootstrap-modal'),
            modalOther = $('.template-modal-other'),
            other = $('.template-other');

        person.getTmpl = function(list) {
            var out = {};
            list.each(function(index, el) {
                var self = $(this);
                out[self.attr('id')] = _.template(self.html());
            });
            return out;
        };

        common.init = function() {

        };

        common.modal = person.getTmpl(modal);
        common.modalBts = person.getTmpl(modalBts);
        common.modalOther = person.getTmpl(modalOther);
        common.overlay = _.template($('#tmpl__overlay').html());
        common.other = person.getTmpl(other);

        return common;
    })();

    BG.tmpl.init();

    BG.MAP_LOADED = false;
    BG.MAP = function() {
        BG.MAP_LOADED = true;
    };

    /**
     * Асинхронная загрузка шрифтов
     * Список шрифтов определяется в BG.fontArray
     */
    BG.fontLoading = (function() {
        var person = {},
            common = {};

        person.addScript = function() {
            var script = document.createElement('script');
            script.src = '/static/public/js/fontfaceobserver.js';
            script.async = true;

            script.onload = function () {
                var i = 0,
                    len,
                    promises = [];

                for (i = 0, len = BG.fontArray.length; i < len; i++) {

                    promises[i] = new FontFaceObserver(BG.fontArray[i].name, {
                        weight: BG.fontArray[i].weight
                    });

                }

                $.when.apply($, promises).done(function() {
                    BG.STORE.dom.d.removeClass('font-loading');
                });
            };

            document.head.appendChild(script);
        };

        common.init = function() {

            if (BG.fontArray === undefined) return;

            person.addScript();
        };

        return common;
    })();

    BG.fontLoading.init();

});