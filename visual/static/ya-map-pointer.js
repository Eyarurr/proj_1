/**
 * Плагин, создающий инструмент для выбора точки на карте. Пишет координаты точки в input'ы,
 * чьи jQuery-объекты переданы в первых двух параметрах.
 * 
 * Пример:
 * 
 * <div id="map" style="width:500px; height:500px;"></div>
 * <button id="remove-marker">Удалить точку на карте</button>
 * <input type="hidden" name="lat" id="lat">
 * <input type="hidden" name="lon" id="lon">
 * 
 * $('#map').yaMapPointer($('#lat'), $('#lon'), {removeMarkButton: $('#remove-marker')})
 */
(function($) {
    $.fn.yaMapPointer = function($lat, $lon, options) {
        var settings = $.extend({
            centerLat: 55.76,
            centerLon: 37.64,
            initialZoom: 11,
            removeMarkButton: false,
        }, options), $map = this, map, placemark;

        function init_map(div) {
            var center;
            if($lat.val() && $lon.val()) {
                center = [$lat.val(), $lon.val()];
            } else {
                center = [settings.centerLat, settings.centerLon];
            }

            map = new ymaps.Map(div, {
                center: center,
                zoom: settings.initialZoom
            });

            if($lat.val && $lon.val()) {
                create_placemark(center);
            } else {
                if(settings.removeMarkButton) settings.removeMarkButton.hide();
            }

            map.events.add('click', function(e) {
                map_update(e.get('coords'));
            });
        }

        function create_placemark(coords) {
            placemark = new ymaps.Placemark(coords, {}, {preset: 'islands#violetStretchyIcon', draggable: true});
            placemark.events.add('dragend', function(e) {
                map_update(placemark.geometry.getCoordinates());
            });
            map.geoObjects.add(placemark);
            if(settings.removeMarkButton) settings.removeMarkButton.show();
        }

        function map_update(coords) {
            if(!placemark) {
                create_placemark(coords);
            }
            placemark.geometry.setCoordinates(coords);

            $lat.val(coords[0]);
            $lon.val(coords[1]);
        }

        if(settings.removeMarkButton) {
            settings.removeMarkButton.click(function() {
                $lat.val('');
                $lon.val('');
                map.geoObjects.remove(placemark);
                placemark = null;
                settings.removeMarkButton.hide();
            });
        }

        ymaps.ready(function() { init_map($map[0]) });
    }
})(jQuery);
