'use strict';

$(function() {

    /**
     * Модуль парсинга данных
     */

    BG.parser = (function() {
        var person = {},
            common = {},

            SMALLEST_VALUE_PIE = 1,
            MAX_VALUES_PIE = 10;

        /**
         * Конструктор хранилища для данных поля values (в виде массива)
         * @param {object} obj Ответ от API
         * @param {string} name Название поля группировки
         */
        var DatasetValues = function(obj, name) {
            this.names = obj[name];
            this.store = this.names.map(function(elem, index) {
                var newElem = {};
                newElem[name] = elem;
                return newElem;
            });
        };

        /**
         * Добавление данных
         * @param {array} from
         * @param {string} what
         * @param {string} key Идентификатор данных вида "tour_id" или "estate_id" (при множественном выборе)
         */
        DatasetValues.prototype.add = function(from, what, key) {
            var self = this,
                key = key || what;

            self.names.forEach(function(elem, index) {
                self.store[index][key || 'visits'] = what ? from[index][what] : from[index];
            });
        };

        /**
         * Возвращает данные
         * @return {array}
         */
        DatasetValues.prototype.get = function() {
            return this.store;
        };

        /**
         * Конструктор хранилища для данных поля total (в виде объекта)
         */
        var DatasetTotal = function(obj, names, fieldName) {
            var self = this;

            self.names = names;
            self.fieldName = fieldName;
            self.store = {};

            self.names.forEach(function(elem, index) {
                self.store[elem] = {};
                self.store[elem][fieldName] = elem;
            });
        };

        /**
         * Добавление набора данных
         * @param {array} from Массив поля total
         * @param {string} what
         * @param {string} key Идентификатор данных вида "tour_id" или "estate_id" (при множественном выборе)
         */
        DatasetTotal.prototype.add = function(from, what, key) {
            var self = this,
                key = key || what;

            from.forEach(function(elem, index) {
                // пропускаем непересекающиеся элементы
                if (self.names.indexOf(elem[self.fieldName]) < 0) return;
                self.store[elem[self.fieldName]][key] = elem[what];
            });
        };

        /**
         * Возвращает данные
         * @return {array}
         */
        DatasetTotal.prototype.get = function() {
            return _.values(this.store);
        };

        /**
         * Обработка данных хранилища
         * @return {array}
         */
        DatasetTotal.prototype.handle = function(func) {
            var self = this,
                id;
            for (id in self.store) {
                func(self.store[id], id);
            };
        };

        function tableTraffic(answer, params) {
            var data;

            // данные будут подвергаться модификации, поэтому следует их склонировать
            data = BG.common.cloneDeep(answer);

            // форматируем даты в соответствии с выбранным периодом группировки
            // common.formatDates(data['date'], params['group']);
            if (data['date']) data['date'] = common.formatDates(data['date'], params['group']);

            return data;
        };

        function tableGeo(answer, params) {
            var data;

            // данные будут подвергаться модификации, поэтому следует их склонировать
            data = BG.common.cloneDeep(answer);

            // // форматируем даты в соответствии с выбранным периодом группировки
            // // вынесем логику в js, чтобы не дублировать её от шаблона к шаблону
            // if (data['date']) data['date'] = common.formatDates(data['date'], params['group']);

            return data;
        };

        function tableTime(answer, params) {
            var data;

            // данные будут подвергаться модификации, поэтому следует их склонировать
            data = BG.common.cloneDeep(answer);

            return data;
        };

        function tableSources(answer, params) {
            var data;

            // данные будут подвергаться модификации, поэтому следует их склонировать
            data = BG.common.cloneDeep(answer);

            return data;
        };

        /**
         * Ограничитель для массивов с текстовыми данными, добавляет последним элементом «Другие»
         * @return {array}
         */
        function limitLabels(list, max) {
            var out = list
                        .slice(0, max)
                        .concat(BG.CONST.STAT.FIELDS['others']);
            return out;
        };

        /**
         * Ограничитель для массивов с числовыми данными, добавляет последним элементом сумму не вошедших элементов
         * @return {array}
         */
        function limitValues(list, max) {
            var out;

            out = list
                    .slice(0, max)
                    .concat(
                        list
                            .slice(MAX_VALUES_PIE, list.length)
                            .reduce(function(prevValue, curValue, index, array) {
                                return prevValue + curValue;
                            })
                    );

            return out;
        };

        /**
         * Возвращает количество туров
         * @return {integer}
         */
        function getCountTours(data) {
            return _.size(data.tours);
        };

        /**
         * Возвращает количество объектов
         * @return {integer}
         */
        function getCountEstates(data) {
            return _.size(data.estates);
        };

        /**
         * Применение функции к турам и объектам
         * Может использоваться как для агрегации данных в единый массив, так и простого перебора всех туров/объектов
         *
         * @param {integer} count Счетчики количества туров и объектов
         * @param {object} data Ответ от API
         * @param {function} func Функция-действие
         * @param {object} params Доп. параметры (в том числе для произвольного алгоритма накапливания результата)
         * @return {array}
         */
        function applyActionForEach(func, data, count, params) {
            var result = [],
                tmpTours,
                tmpEstates;

            // обходим все туры и объекты
            if (count.tours > 0) tmpTours = actionLoop(func, data, 'tours', count, params);
            if (count.estates > 0) tmpEstates = actionLoop(func, data, 'estates', count, params);

            // если функции возвращают массив данных, то склеиваем всё в один массив
            if (tmpTours) result = result.concat(tmpTours);
            if (tmpEstates) result = result.concat(tmpEstates);

            return result;
        };

        /**
         * Обработка каждого тура/объекта
         */
        function actionLoop(func, data, source, count, params) {
            var id,
                result = [],
                tmp;
            for (id in data[source]) {
                tmp = func(data[source][id], id, source, count, params);
                if (tmp) result = result.concat(tmp);
            };
            return result;
        };

        /**
         * Возвращает объект со счётчиками
         */
        function getCounts(data) {
            var result = {};
            result.tours = getCountTours(data);
            result.estates = getCountEstates(data);
            result.all = result.tours + result.estates;
            return result;
        };

        /**
         * Возвращает массив уникальных значений оси категорий
         * @return {array}
         */
        function getAllLabels(fieldName, data, count) {
            var params = {fieldName: fieldName};
            return _.uniq(applyActionForEach(getAllLabelsStep, data, count, params));
        };

        /**
         * Возвращает массив со значениями поля
         * @return {array}
         */
        function getAllLabelsStep(arr, id, source, count, params) {
            return _.pluck(arr.total, params.fieldName);
        };

        /**
         * Возвращает массив общих значений оси категорий
         * пересекающиеся между всеми выбранными турами/объектами
         * @param {string} fieldName Идентификатор собираемого поля
         * @param {object} data Ответ от API
         * @param {object} count Счётчики туров/объектов
         * @return {array}
         */
        function getIntersectLabels(fieldName, data, count) {
            var result,
                output = {store: null, fieldName: fieldName};

            // перебираем все туры/объекты
            applyActionForEach(getIntersectLabelsStep, data, count, output);
            // удаляем дубли, поскольку агрегируются данные в том числе по нескольким турам/объектам
            result = _.uniq(output.store);

            return result;
        };

        /**
         * Итерация вычисления пересечения текущего тура/объекта
         * @param {object} output       Хранилище с доп. параметрами (в том числе для прокидывания данных с предыдущего шага)
         *                 fieldName    — название собираемого поля
         *                 store        — результат с предыдущего шага
         * @return {void}
         */
        function getIntersectLabelsStep(arr, id, source, count, output) {
            var group = [],
                fieldName = output.fieldName,
                intersect = output.store;

            // формируем массив из пар город+страна
            arr.total.forEach(function(elem, index) {
                group.push(elem[fieldName]);
            });

            // вычисляем пересекающиеся элементы между выбранными турами/объектами
            intersect
                ? intersect = _.intersection(intersect, group)
                : intersect = group;

            output.store = intersect;
        };

        /**
         * Формирование данных для графика «Посещаемость»
         * тип bar или line вне зависимости от количества выбранных туров/объектов
         */
        function chartTraffic(answer, params) {
            var result = {},
                count = {},
                dsets,
                labels,
                data;

            // данные будут подвергаться модификации, поэтому следует их склонировать
            data = BG.common.cloneDeep(answer);

            /**
             * Генерация подписей к наборам данных
             */
            function getGraphs(arr, id, source, count, params) {
                var result = [];
                if (count.all === 1) {

                    if (params.columns) {

                        // передан список включенных колонок
                        if (params.columns.indexOf('users') >= 0) result.push('users');
                        if (params.columns.indexOf('visits') >= 0) result.push('visits');
                    } else {

                        result.push('users');
                        result.push('visits');
                    }

                } else {
                    result.push(source + '_' + id);
                }
                return result;
            };

            /**
             * Генерация наборов данных
             * Если всего один тур/объект — посетители + визиты
             * Если несколько — только посетители
             */
            function getDatasets(arr, id, source, count, params) {
                if (count.all === 1) {
                    params['store'].add(arr.values, 'users');
                    params['store'].add(arr.values, 'visits');
                } else {
                    params['store'].add(arr.values, 'users', source + '_' + id);
                }
            };

            console.time('Parsed for chart traffic');

            // подсчёт количества туров и объектов
            count = getCounts(data);
            // названия полей для каждого набора данных
            result['graphs'] = applyActionForEach(getGraphs, data, count, {columns: BG.tableStat.getEnabledColumns()});
            // сами наборы данных со значениями
            result['datasets'] = new DatasetValues(data, 'date');
            applyActionForEach(getDatasets, data, count, {store: result['datasets']});
            // датасеты принимают вид:
            // {
            //     date: '',
            //     tour_234: '',
            //     estate_345: ''
            // }

            console.timeEnd('Parsed for chart traffic');

            return result;
        };

        /**
         * Формирование данных для графика «География»
         * Если только один тур/объект — тип графика pie,
         * если несколько — тип column
         */
        function chartGeo(answer, params) {
            var result = {},
                c = 0,
                count = {},
                labels = [],
                errors = [],
                data;

            // данные будут подвергаться модификации, поэтому следует их склонировать
            data = BG.common.cloneDeep(answer);

            /**
             * Возвращает строку в формате "Город, Страна"
             * @return {string}
             */
            function glueCityAndCountry(arr, id, source, count) {
                arr.total = arr.total.map(function(elem, index) {
                    return elem.city_country ? elem : {
                        city_country: getLabel(elem.city, elem.country),
                        visits: elem.visits
                    };
                });
            };

            /**
             * Возвращает строку в формате "Город, Страна"
             * @return {string}
             */
            function getLabel(city, country) {
                return city === country ? (city || BG.CONST.STAT.FIELDS['others']) : (city || BG.CONST.STAT.FIELDS['others']) + ', ' + country;
            };

            /**
             * Генерация наборов данных
             */
            function getDatasets(arr, id, source, count, params) {
                count.all === 1
                    ? params['store'].add(arr.total, 'visits')
                    : params['store'].add(arr.total, 'visits', source + '_' + id);
            };

            /**
             * Генерация подписей к наборам данных
             */
            function getGraphs(arr, id, source, count) {
                var result = [];
                count.all === 1
                    ? result.push('visits')
                    : result.push(source + '_' + id);
                return result;
            };

            /**
             * Группируем значения менее 0.5% в Другие
             */
            function groupSmallestValues(arr, id, source, count, output) {
                var group = {},
                    summary = 0;

                summary = getSummaryField(arr.total, 'visits');

                arr.total.forEach(function(elem, index) {
                    var val = elem.visits,
                        key;

                    if (val / summary * 100 > SMALLEST_VALUE_PIE) {
                        key = elem.city_country;
                    } else {
                        key = BG.CONST.STAT.FIELDS['others'];

                        // удаляем ненужные лейблы
                        // блок Другие оставляет даже если он мелкий
                        if (elem.city_country !== BG.CONST.STAT.FIELDS['others']) {
                            output.labels.splice(output.labels.indexOf(elem.city_country), 1);
                        }
                    }

                    group[key] === undefined
                        ? group[key] = {city_country: key, visits: elem.visits}
                        : group[key].visits += elem.visits;
                });

                arr.total = _.values(group);
            };

            // подсчёт количества туров и объектов
            count = getCounts(data);

            // преобразуем данные, чтобы город и страна стали склееными
            applyActionForEach(glueCityAndCountry, data, count);

            // // все значения оси категории
            // result.labels = getAllLabels('city_country', data, count)
            // пересекающиеся подписи
            result.labels = getIntersectLabels('city_country', data, count);
            // если пересекающихся лейблов не оказалось
            // значит сравнивать визуально нечего
            if (result.labels.length === 0) errors.push(BG.CONST.STAT.MESSAGES.INTERSECTION_EMPTY);

            // объединим значения меньше 0,5% в другие
            if (params.type === 'pie') applyActionForEach(groupSmallestValues, data, count, result);

            // названия полей для каждого набора данных
            result['graphs'] = applyActionForEach(getGraphs, data, count);
            // сами наборы данных
            result['datasets'] = new DatasetTotal(data, result.labels, 'city_country');
            applyActionForEach(getDatasets, data, count, {store: result['datasets']});

            // возвращаем ошибки
            if (errors.length) result['errors'] = errors;

            console.timeEnd('Parsed for chart geo');

            return result;
        };

        /**
         * Возвращает сумму поля fieldName элементов массива arr
         */
        function getSummaryField(arr, fielName) {
            if (arr.length == 0) return 0;
            if (arr.length == 1) return arr[0][fielName];
            return arr.reduce(function(prev, current) {
                return typeof prev === 'number' ? prev + current[fielName] : prev[fielName] + current[fielName];
            });
        };

        /**
         * Формирование данных для графика «Время просмотра»
         */
        function chartTime(answer, params) {
            var result = {},
                c = 0,
                count,
                labels,
                data;

            // данные будут подвергаться модификации, поэтому следует их склонировать
            data = BG.common.cloneDeep(answer);

            /**
             * Генерация подписей к наборам данных
             */
            function getGraphs(arr, id, source, count) {
                var result = [];
                count.all === 1
                    ? result.push('visits')
                    : result.push(source + '_' + id);
                return result;
            };

            /**
             * Генерация наборов данных
             */
            function getDatasets(arr, id, source, count, params) {
                count.all === 1
                    ? params['store'].add(arr.values, null)
                    : params['store'].add(arr.values, null, source + '_' + id);
            };

            console.time('Parsed for chart time');

            // подсчёт количества туров и объектов
            count = getCounts(data);
            // названия полей для каждого набора данных
            result['graphs'] = applyActionForEach(getGraphs, data, count);
            // сами наборы данных со значениями
            result['datasets'] = new DatasetValues(data, 'time');
            applyActionForEach(getDatasets, data, count, {store: result['datasets']});

            console.timeEnd('Parsed for chart time');

            return result;
        };

        /**
         * Формирование данных для графика «Источники»
         * один тур/объект — тип pie и column-stack
         * несколько туров/объектов — тип line
         */
        function chartSources(answer, params) {
            var result = {},
                count,
                labels = [],
                errors = [],
                data;

            /**
             * Генерация подписей к наборам данных
             */
            function getGraphs(arr, id, source, count) {
                var result = [];
                if (count.all === 1) {
                    result.push('iframe_true');
                    result.push('iframe_false');
                } else {
                    result.push(source + '_' + id);
                }
                return result;
            };

            /**
             * Генерация наборов данных для типа графика pie.
             * Возвращает результат в поле параметра output.store.
             */
            function getDatasetsPie(arr, id, source, count, output) {
                count.all === 1
                    ? output.store.add(arr.total, 'visits')
                    : output.store.add(arr.total, 'visits', source + '_' + id);
            };

            /**
             * Генерация наборов данных для типа графика column.
             * Возвращает результат в поле параметра output.store.
             */
            function getDatasetsColumn(arr, id, source, count, output) {
                if (count.all === 1) {
                    output.store.add(arr.total, 'iframe_true');
                    output.store.add(arr.total, 'iframe_false');
                } else {
                    output.store.add(arr.total, 'visits', source + '_' + id);
                }
            };

            /**
             * Возвращает массив со значениями поля referer_host секции total
             * @param {object} arr Ссылка на данные
             * @param {integer} id Идентификатор тура/объекта
             * @param {string} source Тип данных: tours или estates
             * @param {object} count Счётчики количества туров и объектов
             * @return {array}
             */
            function getRefererHosts(arr, id, source, count) {
                return _.pluck(arr.total, 'referer_host');
            };

            /**
             * Подписываем неопределенные источники
             */
            function updateEmptyLabel(dsets) {
                dsets.handle(function(elem, index) {
                    if (elem.referer_host === '') {
                        elem.referer_host = BG.CONST.STAT.FIELDS['not_defined'];
                    }
                });
            };

            function modifySourceData(data, type, output) {

                if (type === 'pie') {
                    // сгруппируем по referer_host без учёта значения поля iframe
                    applyActionForEach(groupByHostWithoutIframe, data, count);
                    // объединим значения меньше 0,5% в другие
                    applyActionForEach(groupSmallestValues, data, count, output);
                } else {
                    if (count.all === 1) {
                        // сгруппируем по referer_host с учётом значения поля iframe
                        applyActionForEach(groupByHostWithIframe, data, count);
                    } else {
                        // сгруппируем по referer_host без учёта значения поля iframe
                        applyActionForEach(groupByHostWithoutIframe, data, count);
                    }
                }
            };

            /**
             * Группируем записи по полю referer_host. В топе могут встречаться записи
             * с однаковым referer_host, но с разными значениями iframe
             */
            function groupByHostWithoutIframe(arr, id, source, count) {
                var group = {};

                arr.total.forEach(function(elem, index) {
                    var key = elem.referer_host;

                    group[key] === undefined
                        ? group[key] = {referer_host: key, visits: elem.visits}
                        : group[key].visits += elem.visits;
                });

                arr.total = _.values(group);
            };

            /**
             * Группируем значения менее 0.5% в Другие
             */
            function groupSmallestValues(arr, id, source, count, output) {
                var group = {},
                    summary = 0;

                summary = getSummaryField(arr.total, 'visits');

                arr.total.forEach(function(elem, index) {
                    var val = elem.visits,
                        key;

                    if (val / summary * 100 > SMALLEST_VALUE_PIE) {
                        key = elem.referer_host;
                    } else {
                        key = BG.CONST.STAT.FIELDS['others'];

                        // удаляем ненужные лейблы
                        // блок Другие оставляет даже если он мелкий
                        if (elem.referer_host !== BG.CONST.STAT.FIELDS['others']) {
                            output.labels.splice(output.labels.indexOf(elem.referer_host), 1);
                        }
                    }

                    group[key] === undefined
                        ? group[key] = {referer_host: key, visits: elem.visits}
                        : group[key].visits += elem.visits;
                });

                arr.total = _.values(group);
            };

            /**
             * Создаем в каждой записи отдельные значения iframe_true и iframe_false
             */
            function groupByHostWithIframe(arr, id, source, count) {
                var group = {};

                arr.total.forEach(function(elem, index) {
                    var key = elem.referer_host;

                    if (group[key] === undefined) {
                        group[key] = {
                            referer_host: key,
                            iframe_true: 0,
                            iframe_false: 0
                        }
                    }

                    elem.iframe
                        ? group[key].iframe_true += elem.visits
                        : group[key].iframe_false += elem.visits;
                });

                arr.total = _.values(group);
            };

            console.time('Parsed for chart sources.');

            // данные будут подвергаться модификации, поэтому следует их склонировать
            data = BG.common.cloneDeep(answer);

            // подсчёт количества туров и объектов
            count = getCounts(data, params.type);

            // // все значения оси категории
            // result.labels = getAllLabels('referer_host', data, count)
            // пересекающиеся значения оси категории
            result.labels = getIntersectLabels('referer_host', data, count);
            // если пересекающихся лейблов не оказалось
            // значит сравнивать визуально нечего
            if (result.labels.length === 0) errors.push(BG.CONST.STAT.MESSAGES.INTERSECTION_EMPTY);

            // модифицируем данные в зависимости от типа графика
            modifySourceData(data, params.type, result);

            // названия полей для каждого набора данных
            // требуется только для графика типа column
            result['graphs'] = applyActionForEach(getGraphs, data, count);

            // сами наборы данных
            result['datasets'] = new DatasetTotal(data, result.labels, 'referer_host');

            if (params.type === 'pie') {
                applyActionForEach(getDatasetsPie, data, count, {store: result['datasets']});
            } else {
                applyActionForEach(getDatasetsColumn, data, count, {store: result['datasets']});
            }

            // подпишем неопределенные источники
            updateEmptyLabel(result.datasets);

            // возвращаем ошибки
            if (errors.length) result['errors'] = errors;

            console.timeEnd('Parsed for chart sources.');

            return result;
        };

        /**
         * Публичные методы
         */
        common.table = {
            traffic: function(data, params) {
                return tableTraffic(data, params);
            },
            geo: function(data, params) {
                return tableGeo(data, params);
            },
            time: function(data, params) {
                return tableTime(data, params);
            },
            sources: function(data, params) {
                return tableSources(data, params);
            }
        };

        /**
         * Возвращает массив dataset-ов
         */
        common.chart = {
            traffic: function(data, params) {
                return chartTraffic(data, params);
            },
            geo: function(data, params) {
                return chartGeo(data, params);
            },
            time: function(data, params) {
                return chartTime(data, params);
            },
            sources: function(data, params) {
                return chartSources(data, params);
            }
        };

        common.isEmpty = {
            traffic: function(data) {

                function testEmpty(type) {
                    var id,
                        empty = true;

                    // если длина массива из ключей нулевая, значит пусто
                    if (!_.keys(data[type]).length) return empty;

                    // если найдётся хотя бы один элемент с ненулевой длиной массива values
                    // значит данные есть, возвращаем false
                    for (id in data[type]) {
                        empty = empty && data[type][id].values.length === 0;
                    }

                    return empty;
                };

                return !!(testEmpty('tours') & testEmpty('estates'));
            },
            geo: function(data) {

                function testEmpty(type) {
                    var id,
                        empty = true;

                    // если длина массива из ключей нулевая, значит пусто
                    if (!_.keys(data[type]).length) return empty;

                    // если найдётся хотя бы один элемент с ненулевой длиной массива total
                    // значит данные есть, возвращаем false
                    for (id in data[type]) {
                        empty = empty && !data[type][id].total.length
                    }

                    return empty;
                };

                return !!(testEmpty('tours') & testEmpty('estates'));
            },
            time: function(data) {

                function testEmpty(type) {
                    var id,
                        empty = true;

                    // если найдётся хотя бы один элемент, в котором хотя бы одно значение будет не нулевое
                    // значит данные есть, возвращаем false
                    for (id in data[type]) {
                        empty = empty && _.uniq(data[type][id].values)[0] === 0;
                    }

                    return empty;
                };

                return !!(testEmpty('tours') & testEmpty('estates'));
            },
            sources: function(data) {

                function testEmpty(type) {
                    var id,
                        empty = true;

                    // если длина массива из ключей нулевая, значит пусто
                    if (!_.keys(data[type]).length) return empty;

                    // если найдётся хотя бы один элемент с ненулевой длиной массива total
                    // значит данные есть, возвращаем false
                    for (id in data[type]) {
                        empty = empty && !data[type][id].total.length
                    }

                    return empty;
                };

                return !!(testEmpty('tours') & testEmpty('estates'));
            }
        };

        /**
         * Форматирование дат в соответствии с выбранным периодом группировки
         * @param {object} data Данные, обрабатываем только поле date
         * @param {string} group Выбранная детализация по времени
         * @return {object}
         */
        common.formatDates = function(datesList, group) {
            var output = datesList,
                i;

            // если нет группировки по датам
            if (!datesList) return;

            output = datesList.map(function(el, index) {
                var item = el;

                item = moment(item, 'YYYY-MM-DD HH:mm:ss');

                switch (group) {
                    case 'hours':
                        item = item.format('HH:mm, D MMMM');
                        break;

                    case 'days':
                        item = item.format('D MMMM YYYY');
                        break;

                    case 'years':
                        item = item.format('YYYY');
                        break;

                    case 'months':
                    default:
                        item = item.format('MMMM YYYY');
                        break;
                };

                return item;
            });

            return output;
        };

        /**
         * Возвращает название тура, объекта или поля
         * @return {string}
         */
        common.getHumanLabel = function(name) {
            var result,
                nameArr = name.split('_'),
                isTour = nameArr[0] === 'tours',
                isEstate = nameArr[0] === 'estates';

            if (isTour) {
                result = BG.categoryList.getTitleById('tours', nameArr[1]);
            } else if (isEstate) {
                result = BG.categoryList.getTitleById('estates', nameArr[1]);
            } else {
                result = BG.CONST.STAT.FIELDS[name];
            }

            return result;
        };

        return common;
    })();
});