'use strict';

$(function() {

    $.fn.btnGroupRadio = function(options) {
        var settings = $.extend({}, options),
            BC = 'btn-group',
            clActive = 'active',
            groups = $(this);

        if (settings.active === undefined) {

            // инициализация
            groups.on('click', 'input[type="radio"]', function(e) {
                var self = $(this),
                    btn = self.parent(),
                    group = self.closest('.' + BC);

                if (btn.hasClass('active')) {
                    e.preventDefault();
                    return;
                }

                btn.siblings().removeClass(clActive).end().addClass(clActive);
                group.trigger('updated', [self.val()]);
            });

            groups.each(function(index, el) {
                var self = $(this),
                    active = self.data('init');

                if (active === undefined) return;
                self.find('.btn').eq(active).addClass(clActive).find('input[type="radio"]').prop('checked', true);
            });
        } else {

            // выделение активного инпута по значению value
            groups.each(function(index, el) {
                var self = $(this),
                    active;

                active = self.find('input[type="radio"][value="' + settings.active + '"]');
                if (!active.length) return;
                active.prop('checked', true).parent().siblings().removeClass(clActive).end().addClass(clActive);
            });
        }

        return groups;
    };

    $('.btn-group.js-radio').btnGroupRadio();
});