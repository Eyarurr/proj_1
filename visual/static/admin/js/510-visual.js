'use strict';

$(function() {
    BG.visual = (function() {
        var person = {},
            common = {},
            w = $(window),
            body = $('body'),
            resp = '',
            flagValignListPortfolio = false;

        person.resize = function() {
            // Set resolution class
            w.on('load resize', function() {
                person.setResp();
            });
        };

        person.setResp = function() {
            var wW = window.innerWidth, //w.width(),
                newResp;

            body.removeClass('b-page__lg b-page__md b-page__sm b-page__xs b-page__xxs');
            if (wW >= BG.CONST.RESP.MD) {
                body.addClass('b-page__lg');
                newResp = 'lg';
            } else {
                if (wW >= BG.CONST.RESP.SM) {
                    body.addClass('b-page__md');
                    newResp = 'md';
                } else {
                    if (wW >= BG.CONST.RESP.XS) {
                        body.addClass('b-page__sm');
                        newResp = 'sm';
                    } else {
                        if (wW > BG.CONST.RESP.XXS) {
                            body.addClass('b-page__xs');
                            newResp = 'xs';
                        } else {
                            body.addClass('b-page__xxs');
                            newResp = 'xxs';
                        }
                    }
                }
            }

            if (resp !== newResp) {
                resp = newResp;
                BG.STORE.dom.d.trigger('bg.resize', resp);
            }
        };

        // вставка svg картинок инлайном
        person.svgIco = function() {
            if (!Modernizr.svg || !window['svg4everybody']) return;

            svg4everybody({
                polyfill: true
            });
        };

        common.init = function() {
            person.resize();
            person.svgIco();
        };

        common.currentResp = function() {
            if (!resp) person.setResp();
            return resp;
        };

        return common;
    })();

    BG.visual.init();
});
