from flask import render_template, abort, request, current_app

from visual.models import Tour, AggregateCount, AggregateReferer, AggregateTime, AggregateCity
from .. import mod, db


@mod.route('/tours/<int:tour_id>/statistics/')
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/statistics/')
def tour_statistics(tour_id, user_id=None):
    tour = Tour.query.get_or_404(tour_id)
    aggr_type = request.args.get('aggr_type', 'day')

    q = AggregateCount.query.filter_by(tour_id=tour.id, aggr_type=aggr_type).order_by(AggregateCount.date.desc())

    data = q.paginate(per_page=30)

    return render_template('admin/tours/statistics.html', tour=tour, user_id=user_id, data=data, aggr_type=aggr_type)
