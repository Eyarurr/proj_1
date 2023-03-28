'use strict';

$(function() {

    BG.tabsLine = (function() {
        var common = {},

            BC = 'b-tabs-line',

            // dom
            d = BG.STORE.dom.d,
            w = BG.STORE.dom.w,
            b = BG.STORE.dom.b,
            parent,
            tabs;

        function prepareDOM() {

            tabs = $('.' + BC + '__item', parent);
        };

        function bindEvents() {

            if (parent.hasClass('js')) {

                parent.on('click', '.' + BC + '__a', function(e) {
                    var self = $(this),
                        url = self.attr('href'),
                        getParams = parent.data('get-params');

                    e.preventDefault();

                    getParams
                        ? getParams = '?' + getParams
                        : getParams = '';

                    window.location.href = url + getParams;
                });
            }
        };

        common.init = function() {

            parent = $('.' + BC);
            if (!parent.length) return;

            prepareDOM();
            bindEvents();
        };

        common.getCurrentTab = function() {
            return tabs.filter('.active');
        };

        common.setCount = function(block, count) {
            block.find('.' + BC + '__sup').text(count);
        };

        common.setGetParams = function(value) {
            parent.data('get-params', value);
        };

        return common;
    })();

    BG.tabsLine.init();
});
