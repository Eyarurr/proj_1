$.ajaxSetup({
    error: function(xhr, textStatus, errorThrown) {
        alert(
            'Что-то пошло не так! Попробуйте обновить страницу.\n\n' +
            'Ошибка: HTTP ' + xhr.status + ': ' + $(xhr.responseText).text()
        );
    },
    beforeSend: function() {
        $('#ajax-wait').show();
    },
    complete: function() {
        $('#ajax-wait').hide();
    }
});

function apiUrl(method, params) {
    let url = '/api/' + method + '?v=2.0&client=webadmin&client_version=1.0'
    if(params) {
        for(let param in params) {
            url += '&' + param + '=' + params[param];
        }
    }
    return url;
}

function api3Url(method, params) {
    let url = '/api/v3/' + method + '?client=site.admin&client_version=1.0'
    if(params) {
        for(let param in params) {
            url += '&' + param + '=' + params[param];
        }
    }
    return url;
}


/**
 * Наполняет <select> опциями, в зависимости от значения другого поля:
 *
 * $('#subtype').dependentSelect({
 *      master: $('#type'),
 *      values: {
 *          'type1': [['1-1', 'subtype 1-1'], ['1-2', 'subtype 1-2']],
 *          'type2': [['2-1', 'subtype 2-1'], ['2-2', 'subtype 2-2']],
 *      }
 * });
 */
(function($) {
    $.fn.dependentSelect = function (options) {
        var settings = $.extend({
            master: null,
            values: {},
            'default': null,
        }, options), $dependent = this;

        function setOptions() {
            var masterVal = settings.master.val();
            $dependent.find('option').remove();
            if (!masterVal) return;
            for (var i = 0; i < settings.values[masterVal].length; i++) {
                $('<option>').attr('value', settings.values[masterVal][i][0]).text(settings.values[masterVal][i][1]).appendTo($dependent);
            }

            if(settings.default) $dependent.val(settings.default);
        }

        settings.master.change(setOptions).change();

        return this;
    }
})(jQuery);


/**
 * Новости
 */
$(function() {
    var $toggler = $('.navbar .link-news'), $pane = $('#news-pane'), $feed = $pane.find('.news-feed');

    $toggler.click(function(e) {
        e.preventDefault();
        $pane.toggle();
        if($pane.is(':visible')) {
            $feed
                .html('<p class="text-center"><i class="fas fa-spinner fa-spin fa-4x"></i></p>')
                .load('/admin/news/?mode=feed', function() {
                    $toggler.removeClass('new').find('sup').remove();
                });
        }
    });

});

$(function() {
    var body = $('body'),
        modalLangsDelete = $('#modal-langs-delete');

    // input-i18n
    (function() {

        function bindEvents() {
            var paramItem;

            body
                .on('click', 'span.input-i18n__lang', function(e) {
                    var self = $(this),
                        item = self.closest('.input-i18n__item');

                    if (!item.siblings('.input-i18n__item').length) return;

                    toggle(item);
                    create(item);
                })
                .on('click', 'a.input-i18n__lang', function(e) {
                    paramItem = $(this).closest('.input-i18n__item');
                    modalLangsDelete.data('lang', paramItem.data('lang')).data('type', 'input').modal('show');
                })
                .on('click', '.input-i18n__toggle', function(e) {
                    var self = $(this),
                        parent = self.closest('.input-i18n'),
                        isFolded = parent.attr('data-folded');

                    e.preventDefault();

                    isFolded == undefined || isFolded == 0
                        ? parent.attr('data-folded', 1)
                        : parent.attr('data-folded', 0);
                })
                .on('click', '.input-i18n__disable', function(e) {
                    var self = $(this),
                        parent = self.closest('.input-i18n');

                    parent.attr('data-standard', +self.prop('checked'));

                    self.prop('checked')
                        ? disable(parent)
                        : enable(parent);
                });

            modalLangsDelete
                .on('shown.bs.modal', function(e) {
                    var self = $(e.relatedTarget);

                    if (modalLangsDelete.data('type') !== 'input') return;

                    modalLangsDelete.find('.lang').text(modalLangsDelete.data('lang'));

                    modalLangsDelete.find('button[data-dismiss]').focus();
                    modalLangsDelete.find('button.btn-danger').on('click', function() {
                        var item = paramItem,
                            parent = item.closest('.input-i18n');

                        parent.attr('data-folded', 0);

                        toggle(item);
                        destroy(item);
                        modalLangsDelete.modal('hide');
                    });
                })
                .on('hide.bs.modal', function(e) {

                    if (modalLangsDelete.data('type') !== 'input') return;
                    modalLangsDelete.find('button.btn-danger').off('click');
                });
        }

        function disable(parent) {
            parent.find('input[type="text"]').prop('disabled', true);
        }

        function enable(parent) {
            var items = $('.input-i18n__item', parent),
                state = parent.attr('data-state');

            items.find('input[type="text"]').prop('disabled', !+state);
            items.filter('.input-i18n__one').find('input[type="text"]').prop('disabled', !!+state);
        }

        // переключение интерфейса
        function toggle(item) {
            var parent = item.closest('.input-i18n'),
                items = $('.input-i18n__item', parent),
                isCommonLang = item.hasClass('input-i18n__one');

            parent.attr('data-state', +isCommonLang);
            items.find('input[type="text"]').prop('disabled', !isCommonLang);
            items.filter('.input-i18n__one').find('input[type="text"]').prop('disabled', isCommonLang);
        }

        // удаление мультиязычности — оставляем только выбранный перевод
        function destroy(item) {
            var value = item.find('input').val();

            item.siblings('.input-i18n__item').andSelf().not('.input-i18n__one').find('input').val('');
            item.siblings('.input-i18n__one').find('input').val(value);
        }

        // добавление мультиязычности — текущее значение переносим в инпут языка тура
        function create(item) {
            var value = item.find('input').val(),
                lang = item.closest('.input-i18n').data('lang') || 'en';

            item.find('input').val('');
            item.siblings('.input-i18n__item').filter('[data-lang="' + lang + '"]').find('input').val(value);
        }

        bindEvents();
    })();

    // area-i18n
    (function() {

        function bindEvents() {
            var parent;

            body.on('click', '.area-i18n__lang', function(e) {
                var self = $(this),
                    isStar,
                    items,
                    index,
                    lang;

                e.preventDefault();

                parent = self.closest('.area-i18n');
                isStar = self.is('span');
                items = $('.area-i18n__item', parent);

                if (items.length <= 1) return;

                if (+parent.attr('data-state')) {

                    if (isStar) {

                        // выбираем перевод, который следует сохранить
                        lang = self.closest('.area-i18n__tabs').find('.is-active').find('.area-i18n__lang').text();
                        // и открываем модальное окно подтверждения удаления всех остальных переводов
                        modalLangsDelete.data('type', 'textarea').data('lang', lang).modal('show');
                    } else {

                        // переключить табов
                        index = self.closest('.area-i18n__tabs').find('.area-i18n__lang').index(self);
                        setTabs(parent, index);
                    }

                } else {

                    if (isStar) {

                        // преобразуем textarea в мультиязычный формат
                        langCreate(parent);
                        toggleState(parent, false);
                        index = items.index(items.filter('[data-lang="' + parent.data('lang') + '"]'));
                        setTabs(parent, index);
                    }
                }
            });

            modalLangsDelete
                .on('shown.bs.modal', function(e) {
                    var lang = modalLangsDelete.data('lang');

                    if (modalLangsDelete.data('type') !== 'textarea') return;

                    modalLangsDelete.find('.lang').text(lang);

                    modalLangsDelete.find('button[data-dismiss]').focus();
                    modalLangsDelete.find('button.btn-danger').on('click', function() {

                        langDestroy(parent, lang);
                        toggleState(parent, true);
                        modalLangsDelete.modal('hide');
                    });
                })
                .on('hide.bs.modal', function(e) {

                    if (modalLangsDelete.data('type') !== 'textarea') return;
                    modalLangsDelete.find('button.btn-danger').off('click');
                });
        }

        function toggleState(parent, isCommonLang) {
            var items = $('.area-i18n__item', parent);

            parent.attr('data-state', +!isCommonLang);
            items.find('textarea').prop('disabled', isCommonLang);
            items.filter('.area-i18n__one').find('textarea').prop('disabled', !isCommonLang);
        }

        function setTabs(parent, target) {
            var tabs = $('.area-i18n__tab', parent),
                items = $('.area-i18n__item', parent);

            tabs.removeClass('is-active').eq(target).addClass('is-active');
            items.removeClass('is-active').eq(target).addClass('is-active');
        }

        // удаление мультиязычности — оставляем только выбранный перевод
        function langDestroy(parent, lang) {
            var items = $('.area-i18n__item', parent),
                value = items.filter('[data-lang="' + lang + '"]').find('textarea').val();

            items.filter('.area-i18n__one').find('textarea').val(value);
            setTabs(parent, 0);
        }

        // добавление мультиязычности — текущее значение переносим в textarea языка тура
        function langCreate(parent) {
            var items = $('.area-i18n__item', parent),
                commonArea = items.filter('.area-i18n__one').find('textarea'),
                value = commonArea.val(),
                lang = parent.data('lang') || 'en';

            commonArea.val('');
            items.filter('.area-i18n__item').filter('[data-lang="' + lang + '"]').find('textarea').val(value);
        }

        bindEvents();
    })();

    // hotkeys
    (function() {
        var DICT = {
            // на циферном блоке клавиатуре
            // 98: '²',    // 2
            // 109: '—',   // -

            // на алфавитно-циферном блоке
            50: '²',    // 2
            173: '—',   // - (для firefox)
            188: '«',   // <
            189: '—',   // -
            190: '»',   // >
        };

        function insertText(el, chars) {
            var text  = el.val(),
                start = el.prop('selectionStart'),
                end = el.prop('selectionEnd'),
                before = text.substring(0, start),
                after = text.substring(end, text.length);

            el.val(before + chars + after);
            el[0].selectionStart = start + chars.length;
            el[0].selectionEnd = el[0].selectionStart;
        }

        $(document).on('keyup', 'input[type="text"], textarea', function(e) {
            var self = $(this);

            if (bowser.safari || bowser.mac) {
                if (DICT[e.which] === undefined || !e.ctrlKey) return;
            } else {
                if (DICT[e.which] === undefined || !e.ctrlKey || !e.altKey) return;
            }

            insertText(self, DICT[e.which]);
        });
    })();
});