import os

from flask import render_template, request, flash, redirect, url_for
from flask_login import current_user

from .. import mod, roles_required
from visual.mail import send_email
from visual.models import RemoteDataset, RemoteEvent
from visual.core import db


@mod.route('/sys/rempote-datasets/', methods=('GET', ))
@roles_required('remote-processing.view')
def sys_remote_datasets():
    datasets = RemoteDataset.query.order_by(RemoteDataset.created.desc()).paginate(per_page=50)

    return render_template('admin/sys/remote_datasets.html', datasets=datasets)


@mod.route('/sys/remote-datasets/<int:dataset_id>')
@roles_required('remote-processing.view')
def sys_remote_dataset(dataset_id):
    dataset = RemoteDataset.query.get_or_404(dataset_id)

    events = RemoteEvent.query\
        .filter_by(dataset_id=dataset.id)\
        .order_by(RemoteEvent.created.desc())\
        .paginate(per_page=50, error_out=False)

    return render_template('admin/sys/remote_dataset.html', dataset=dataset, events=events)