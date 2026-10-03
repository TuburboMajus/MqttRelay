from flask import current_app, render_template, request, redirect, url_for, abort, session, g, jsonify, Blueprint
from flask_login import login_required, current_user

from core.repository import repos
from core.pagination import paginate
from core.models import Metric

from datetime import datetime, date
import logging


bp = Blueprint('metrics', __name__)

def setup(config=None):
    """Setup metrics blueprint with configuration."""
    return bp


@bp.route('/metrics')
@login_required
def listMetrics():
    current_app.logger.debug("Route [metrics.listMetrics] called (page=%s)", request.args.get('page'))
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    pagination = paginate(repos['Metric'], page=page, per_page=per_page)
    
    if request.args.get('json', 'false').lower() in ["1", "true"]:
        return jsonify(pagination.to_dict())
    
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/metrics/list.html",
        pagination=pagination
    )


@bp.route('/metric')
@login_required
def newMetric():
    current_app.logger.debug("Route [metrics.newMetric] serving new metric form")
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/metrics/new.html"
    )


@bp.route('/metric', methods=["POST"])
@login_required
def createMetric():
    current_app.logger.debug("Route [metrics.createMetric] creating metric")
    data = request.form.to_dict() if request.form else request.get_json()
    metric = Metric(
        name=data.get('name'),
        unit=data.get('unit'),
        type=data.get('type') or 'value',
        description=data.get('description'),
        default_unit=data.get('default_unit'),
        active=data.get('active', 'true').lower() in ['true', '1', 'on'] if isinstance(data.get('active', 'true'), str) else bool(data.get('active')),
        created_at=datetime.utcnow()
    )
    repos['Metric'].create(metric)
    current_app.logger.info("Route [metrics.createMetric] metric created (id=%s)", metric.id)
    return jsonify(status="created", metric=metric.to_dict())


@bp.route('/metric/<int:metric_id>')
@login_required
def viewMetric(metric_id):
    current_app.logger.debug("Route [metrics.viewMetric] called (metric_id=%s)", metric_id)
    metric = repos['Metric'].get(id=metric_id)
    if metric is None:
        current_app.logger.warning("Route [metrics.viewMetric] metric not found (id=%s)", metric_id)
        return abort(404)

    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/metrics/view.html",
        metric=metric
    )



@bp.route('/metric/<int:metric_id>', methods=["PUT", "PATCH"])
@login_required
def editMetric(metric_id):
    current_app.logger.debug("Route [metrics.editMetric] called (metric_id=%s)", metric_id)
    metric = repos['Metric'].get(id=metric_id)
    if metric is None:
        current_app.logger.warning("Route [metrics.editMetric] metric not found (id=%s)", metric_id)
        return abort(404)

    data = request.get_json() or request.form.to_dict()
    updatable = {'name', 'unit', 'type', 'description', 'default_unit', 'active'}
    update_dict = {k: v for k, v in data.items() if k in updatable}
    
    # Handle boolean conversion for active field
    if 'active' in update_dict:
        update_dict['active'] = update_dict['active'].lower() in ['true', '1', 'on'] if isinstance(update_dict['active'], str) else bool(update_dict['active'])
    
    repos['Metric'].update(metric, **update_dict)
    current_app.logger.info("Route [metrics.editMetric] metric updated (id=%s)", metric_id)
    return jsonify(status="updated", data=metric.to_dict())


@bp.route('/metric/<int:metric_id>', methods=["DELETE"])
@login_required
def deleteMetric(metric_id):
    current_app.logger.debug("Route [metrics.deleteMetric] called (metric_id=%s)", metric_id)
    metric = repos['Metric'].get(id=metric_id)
    if metric is None:
        current_app.logger.warning("Route [metrics.deleteMetric] metric not found (id=%s)", metric_id)
        return abort(404)

    metric_dict = metric.to_dict()
    repos['Metric'].delete(metric)
    current_app.logger.info("Route [metrics.deleteMetric] metric deleted (id=%s)", metric_id)
    return jsonify(status="deleted", data=metric_dict)