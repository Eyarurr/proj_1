function initMap(){
    let elMap = document.getElementById('map'),
        elLat = document.getElementById('coords_lat'),
        elLon = document.getElementById('coords_lon'),
        elStart = document.getElementById('start'),
        elTTS = document.getElementById('tts'),
        elAddress = document.getElementById('address'),
        coords,
        office_coords = document.getElementById('form-edit').dataset.officeCoords.split(','),
        city_id = document.getElementById('form-edit').dataset.cityId.split(','),
        zoom,
        pointer;
    let elFreeTimeBtn = document.getElementById('btn-get-freetime'),
        elFreetime = document.getElementById('freetime');

    if(elLat.value) {
        coords = [elLat.value, elLon.value];
    }

    function setCoords(coords) {
        elLat.value = coords[0];
        elLon.value = coords[1];
        ymaps.geocode(coords).then(function(res) {
            let obj = res.geoObjects.get(0);
            // Канонический способ - elAddress.value = obj.getAddressLine(); вернёт полный адрес со страной и городом; properties.get('name')
            // может отвалиться, так как автор не нашёл его в документации
            elAddress.value = obj.properties.get('name')
        });
    }

    function createPlacemark(where) {
        pointer = new ymaps.Placemark(where, {}, {draggable: true});
        map.geoObjects.add(pointer);
        pointer.events.add('dragend', function(e) {
            setCoords(e.get('target').geometry.getCoordinates());
        });
    }

    function formatDateTime(d) {
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0') +
            ' ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0') + '+' +
            String(-d.getTimezoneOffset() / 60).padStart(2, '0') + ':00';
    }

    let map = new ymaps.Map(elMap, {
        center: coords ? coords : office_coords,
        zoom: coords ? 17 : 12,
        controls: ['searchControl', 'trafficControl', 'zoomControl']
    });

    if(coords) {
        createPlacemark(coords);
    }

    officePointer = new ymaps.Placemark(office_coords, {iconContent: 'Офис'}, {preset: 'islands#grayStretchyIcon'});
    map.geoObjects.add(officePointer);

    map.events.add('click', function(e) {
        let where = e.get('coords');
        if(pointer) {
            pointer.geometry.setCoordinates(where);
        } else {
            createPlacemark(where);
        }
        setCoords(where);
    });

    document.getElementById('btn-start-now').addEventListener('click', function(e) {
        elStart.value = formatDateTime(new Date());
    });

    elFreeTimeBtn.addEventListener('click', function(e) {
        if(!elLat.value || !elLon.value) {
            alert('Укажите место заказа');
            return;
        }

        if(!parseInt(elTTS.value)) {
            alert('Введите предполагаемое время работы');
            return;
        }

        let s = new Date(elStart.value);
        if(!s) {
            alert('Не получилось разобрать время начала. Введите хотя бы дату в виде ГГГГ-ММ-ДД');
            return;
        }
        let date = s.getFullYear() + '-' + (s.getMonth() + 1) + '-' + s.getDate();

        let qs = {
            client: 'web.admin', client_version: '1.0',
            city_id: city_id,
            coords: elLat.value + ',' + elLon.value,
            tts: elTTS.value,
            date: date
        }

        fetch('/api/v3/bladerunner/freetime?' + new URLSearchParams(qs))
        .then(function(resp) {
            return resp.json();
        })
        .then(function(data) {
            if(data.errors) {
                elFreetime.classList.add('error');
                elFreetime.innerHTML = data.errors.join('<br>');
                return;
            }
            elFreetime.classList.remove('error');
            let html = '<ul>';
            for(slot of data.result) {
                let t1 = new Date(slot[0]);
                let t2 = new Date(slot[1]);
                html += '<li><b>' + formatDateTime(new Date(slot[0])) + '</b> — <b>' + formatDateTime(new Date(slot[1])) + '</b></li>';
            }
            html += '</ul>';
            elFreetime.innerHTML = html;
        });
    });

    elFreetime.addEventListener('click', function(e) {
        elStart.value = e.target.textContent;
    });
}

function initContacts() {
    let elForm = document.getElementById('form-edit'),
        elContacts = document.getElementById('contacts'),
        contacts = [],
        elContactsContainer = document.getElementById('contacts-container'),
        rowTemplate = document.getElementById('contacts-row-template').innerHTML,
        elBtnAdd = document.getElementById('contacts-btn-add');

    if(elContacts.value) {
        contacts = JSON.parse(elContacts.value);
    }
    if(contacts == null) {
        contacts = [];
    }

    for(let contact of contacts) {
        let elRow = document.createElement('div');
        elRow.innerHTML = rowTemplate;
        let elName = elRow.getElementsByClassName('name')[0];
        let elPhone = elRow.getElementsByClassName('phone')[0];
        elName.value = contact.name;
        elPhone.value = contact.phone;
        elContactsContainer.append(elRow);
    }

    elBtnAdd.addEventListener('click', function(e) {
        let elRow = document.createElement('div');
        elRow.innerHTML = rowTemplate;
        elContactsContainer.append(elRow);
    });

    elForm.addEventListener('submit', function(e) {
        // Собираем данные из всех полей для контактов в объект contacts
        contacts = [];
        for(let elRow of elContactsContainer.children) {
            let name = elRow.getElementsByClassName('name')[0].value;
            let phone = elRow.getElementsByClassName('phone')[0].value;
            if(!name && !phone) { continue; }
            contacts.push({name, phone});
        }
        elContacts.value = JSON.stringify(contacts);
    });
};

ymaps.ready(initMap);
initContacts();
