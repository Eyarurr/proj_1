(function() {
    var uploadUrl = $('#upload-token').data('url'), uploadToken = $('#upload-token').data('token'),
        $formTitle = $('#form-title'),
        $formResolutions = $('#form-resolutions'),
        $formResolutionAdd = $('#form-resolution-add'),
        $modalResolutionsAdd = $formResolutionAdd.find('.modal'),
        $formModel = $('#form-model'),
        isModelUploaded = false,
        $barModel = $formModel.find('.progress');

    function processProblems(data) {
        if(!('problems' in data)) return;
        var $ul = $('#problems');
        $ul.empty();
        if(data['problems'].length) {
            $('#btn-build').attr('disabled', true);
        } else {
            $('#btn-build').attr('disabled', false);
        }
        for(var i = 0; i < data['problems'].length; i++) {
            $('<li>').html(data['problems'][i]).appendTo($ul);
        }
    }

    $.ajaxSetup({
        success: processProblems
    });

    // Название
    $formTitle.find('[name=title]').focus();
    $formTitle.ajaxForm();
    $formTitle.find('[name=title]').on('blur', function() {
        $formTitle.submit();
    });

    // Разрешения
    $formResolutions.ajaxForm();

    // Добавить разрешение
    $modalResolutionsAdd.on('shown.bs.modal', function() {
        $formResolutionAdd.find('[name=w]').focus();
    });
    $formResolutionAdd.on('submit', function(e) {
        e.preventDefault();
        var $form = $(this),
            w = $form.find('[name=w]').val().trim(),
            h = $form.find('[name=h]').val().trim(),
            res = w + 'x' + h,
            resText = w + '&times;' + h;

        if(w == '' || h == '') {
            alert('Введите и ширину, и высоту');
            return;
        }
        if(isNaN(w) || isNaN(h)) {
            alert('Только цифры, пожалуйста');
            return;
        }

        // @todo: а тут проверить, нет ли такого разрешения уже

        $('#resolutions-list').append(
            $('<span>')
                .addClass('label label-info')
                .data('resolution', res)
                .append(resText)
                .append(
                    $('<a>').attr('href', '#').append(
                        $('<i>').addClass('fas fa-ban')
                    )
                )
                .append(
                    $('<input>').attr('type', 'hidden').attr('name', 'res').val(res)
                )
        );
        $modalResolutionsAdd.modal('hide');
        $formResolutions.submit();
    });

    // Удалить разрешение
    $formResolutions.on('click', '#resolutions-list a', function(e) {
        e.preventDefault();
        $(this).parents('span.label').remove();
        $formResolutions.submit();
    });

    // Загрузить модель
    $formModel.ajaxForm({
        success: function(data) {
            processProblems(data);
            var $modelInfo = $('#model-info');
            $modelInfo.html(
                data.model + ' ' + Math.round(data.model_size / 1024 / 1024) + ' MB ' +
                '<a href="#modal-model-delete" data-toggle="modal" class="text-danger" title="Удалить"><i class="fas fa-ban"></i></a>'
            );
        }
    });
    var flow = new Flow({
        target: uploadUrl + uploadToken + '-model',
        query: {csrf_token: $formModel.find('[name=csrf_token]').val()},
        withCredentials: true,
        singleFile: true,
        testChunks: false,
        allowDuplicateUploads: true
    });
    flow.assignBrowse($formModel.find('#btn-model-browse')[0], false, true);
    flow.on('filesSubmitted', function(files, event){
        $formModel.find('[name=filename]').val(files[0].name);
        $barModel.show();
        $formModel.find('#btn-model-browse').attr('disabled', true);
        flow.upload();
    });
    flow.on('progress', function() {
        var prc = Math.round(flow.progress() * 100) + '%';
        $barModel.find('.progress-bar').css({'width': prc}).text(prc);
    });
    flow.on('error', function(message, file, chunk){
        alert('При загрузке файла ' + file + ' произошла ошибка: ' + message);
    });
    flow.on('complete', function(){
        isModelUploaded = true;
        $formModel.submit();
    });
    $formModel.on('submit', function(e) {
        if(flow.files.length == 0) {
            return false;
        }

        $barModel.hide();
        $formModel.find('#btn-model-browse').attr('disabled', false);
        $barModel.find('.progress-bar').css({'width': 0}).text('0');
    });

    // Удалить модель
    $('#form-model-delete').ajaxForm({
        success: function(data) {
            processProblems(data);
            $('#modal-model-delete').modal('hide');
            $('#model-info').html('Не загружена.');
        }
    });

    /* Сеты */
    var $setForms = $('#set-forms'),
        $formSetAdd = $('#form-set-add'),
        $formSetDelete = $('#form-set-delete'),
        $formSetTemplate = $('#form-set-template'),
        $formFrameDelete = $('#form-frame-delete'),
        $modalFrameDelete = $('#modal-frame-delete');

    function createFrameList($ul, data) {
        var frame_id, frame, $li;
        $ul.empty();
        for(frame_id in data) {
            frame = data[frame_id];

            $li = $('<li>').data('eye', 'center').data('id', frame_id);
            $li.append('<a href="#modal-frame-delete" data-toggle="modal" title="Удалить фрейм"><i class="fas fa-ban text-danger"></i></a> ');
            $li.append(
                $('<a>').attr('href', frame['url']).attr('target', '_blank').append('' + frame_id + ': ' + frame['filename'])
            );
            if(!('pos' in frame)) {
                $li.append(' <i class="fas fa-exclamation-circle text-danger" title="Нет координаты для этого фрейма!"></i>')
            }
            $ul.append($li);
        }
    }

    function initSetForm() {
        var $form = $(this),
            set_id = $form.data('id'),
            flow,
            $browse = $form.find('.btn-upload'),
            $progress = $form.find('.progress'),
            myUploadToken = uploadToken + '-set-' + set_id;

        flow = new Flow({
            target: uploadUrl + uploadToken + '-set-' + set_id,
            query: { csrf_token: $form.find('[name=csrf_token]').val() },
            withCredentials: true,
            testChunks: false,
            allowDuplicateUploads: true
        });
        flow.assignBrowse($browse[0], false);
        flow.on('filesSubmitted', function(file, event){
            $browse.attr('disabled', true);
            $progress.show();
            flow.upload();
        });
        flow.on('progress', function() {
            var prc = Math.round(flow.progress() * 100) + '%';
            $progress.find('.progress-bar').css({'width': prc}).text(prc);
        });
        flow.on('error', function(message, file, chunk){
            alert('При загрузке файла ' + file + ' произошла ошибка: ' + message);
        });
        flow.on('complete', function(){
            $.ajax({
                method: 'POST',
                url: $form.data('upload-complete-url') + '?token=' + myUploadToken,
                data: {
                    csrf_token: $form.find('[name=csrf_token]').val(),
                    set_id: set_id
                },
                success: function(data) {
                    if(data.errors) {
                        alert(data.errors.join('\n'));
                        return;
                    }
                    processProblems(data);
                    createFrameList($form.find('.frames-list'), data.set.frames);
                }
            });

            $browse.attr('disabled', false);
            $progress.hide();
            $progress.find('.progress-bar').css({'width': 0}).text('0');
        });

        flows[$form.data('id')] = flow;
    }

    function saveSetCallback(data) {
        if(data.errors) {
            alert(data.errors.join('\n\n'));
            return;
        }
        processProblems(data);
        createFrameList($setForms.find('form.form-set[data-id=' + data.set.id + '] .frames-list'), data.set.frames);
    }

    // Свойства сета
    $setForms.find('.form-set').ajaxForm({
        success: saveSetCallback
    });
    var submitForm = function() { $(this).parents('form').submit(); };
    $setForms.on('blur', '.form-set [name=title]', submitForm);
    $setForms.on('blur', '.form-set [name=center]', submitForm);
    $setForms.on('blur', '.form-set [name=coords]', submitForm);

    // Создать сет
    $formSetAdd.ajaxForm({
        success: function(data) {
            processProblems(data);
            var $newForm = $formSetTemplate.clone().attr('id', null);
            $newForm.data('id', data.set.id);
            $newForm.attr('data-id', data.set.id);
            $newForm.find('[name=id]').val(data.set.id);
            $newForm.find('.set-id').text(data.set.id);
            $setForms.append($newForm);
            $newForm.find('[name=title]').focus();

            initSetForm.call($newForm[0]);
            $newForm.ajaxForm({
                success: saveSetCallback
            });
        }
    });

    // Удалить сет
    $formSetDelete.ajaxForm({
        success: function(data) {
            if(data.errors) {
                alert(data.errors.join('\n\n'));
                return;
            }
            processProblems(data);
            $setForms.find('.form-set[data-id=' + data.id + ']').remove();
        }
    });
    $setForms.on('click', 'button.btn-set-delete', function(e) {
        var set_id = $(this).parents('form').data('id');
        if(!confirm('Удалить сет #' + set_id + '?')) return;
        $formSetDelete.find('[name=id]').val(set_id);
        $formSetDelete.submit();
    });

    // Загрузка фреймов
    var flows = {};
    $setForms.find('.form-set').each(initSetForm);

    // Удалить фрейм
    $modalFrameDelete.on('shown.bs.modal', function(e) {
        var $li = $(e.relatedTarget).parents('li');
        $formFrameDelete.find('[name=set_id]').val($li.parents('form').data('id'));
        $formFrameDelete.find('[name=eye]').val($li.data('eye'));
        $formFrameDelete.find('[name=frame_id]').val($li.data('id'));
    });
    $formFrameDelete.ajaxForm({
        success: function(data) {
            if(data.errors) {
                alert(data.errors.join('\n\n'));
                return;
            }
            processProblems(data);

            $modalFrameDelete.modal('hide');
            createFrameList($setForms.find('form.form-set[data-id=' + data.set.id + '] .frames-list'), data.set.frames);
        }
    })

})();