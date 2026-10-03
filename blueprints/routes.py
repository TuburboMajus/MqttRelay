from flask import current_app, render_template, request, redirect, url_for, abort, session, g, jsonify, Blueprint
from flask_login import login_required, current_user

from core.repository import repos
from core.pagination import paginate
from core.models import RoutingRule, RouteDeposit, Parser

from datetime import datetime, date
import logging


bp = Blueprint('routes', __name__)

def setup(config=None):
    """Setup routes blueprint with configuration."""
    return bp


@bp.route('/routes')
@login_required
def listRoutingRules():
    current_app.logger.debug("Route [routes.listRoutingRules] called (json=%s, page=%s)", request.args.get('json'), request.args.get('page'))
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    pagination = paginate(repos['RoutingRule'], page=page, per_page=per_page)
    
    if request.args.get('json', 'false').lower() in ["1", "true"]:
        return jsonify(pagination.to_dict())
    
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/routes/list.html",
        pagination=pagination
    )


@bp.route('/route')
@login_required
def newRoutingRule():
    current_app.logger.debug("Route [routes.newRoutingRule] serving new routing rule form")
    parsers = repos['Parser'].list()
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/routes/new.html",
        parsers=[p.to_dict() for p in parsers]
    )


@bp.route('/route', methods=["POST"])
@login_required
def createRoutingRule():
    current_app.logger.debug("Route [routes.createRoutingRule] creating routing rule")
    data = request.form.to_dict() if request.form else request.get_json()
    
    # Extract destination IDs from array format
    destination_ids = request.form.getlist('destination_ids[]') if request.form else data.get('destination_ids', [])
    
    # Handle empty fields
    for field in ['device_id', 'conditions']:
        if data.get(field, '').strip() == '':
            data[field] = None
    
    routingrule = RoutingRule(
        client_id=data.get('client_id'),
        topic_id=data.get('topic_id'),
        device_id=data.get('device_id'),
        parser_id=data.get('parser_id'),
        parser_config=data.get('parser_config'),
        active=data.get('active', 'on').lower() in ['on', '1', 'true'] if isinstance(data.get('active', 'on'), str) else bool(data.get('active')),
        priority=int(data.get('priority', 0)),
        conditions=data.get('conditions'),
        created_at=datetime.utcnow()
    )
    repos['RoutingRule'].create(routingrule)
    
    # Create route deposits for each destination
    for dest_id in destination_ids:
        deposit = RouteDeposit(
            rule_id=routingrule.id,
            destination_id=int(dest_id),
            created_at=datetime.utcnow()
        )
        repos['RouteDeposit'].create(deposit)
    
    current_app.logger.info("Route [routes.createRoutingRule] routing rule created (id=%s)", routingrule.id)
    return redirect(url_for("routes.listRoutingRules"))


@bp.route('/route/<string:routingrule_id>')
@login_required
def viewRoutingRule(routingrule_id):
    current_app.logger.debug("Route [routes.viewRoutingRule] called (routingrule_id=%s)", routingrule_id)
    routingrule = repos['RoutingRule'].get(id=routingrule_id)
    if routingrule is None:
        current_app.logger.warning("Route [routes.viewRoutingRule] routing rule not found (id=%s)", routingrule_id)
        return abort(404)

    # Fetch route deposits for this rule
    destinations = repos['RouteDeposit'].list(rule_id=routingrule.id)
    
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/routes/view.html",
        rule=routingrule,
        destinations=[d.to_dict() for d in destinations]
    )



@bp.route('/route/<string:routingrule_id>', methods=["PUT", "PATCH"])
@login_required
def editRoutingRule(routingrule_id):
    current_app.logger.debug("Route [routes.editRoutingRule] called (routingrule_id=%s)", routingrule_id)
    data = request.get_json() or request.form.to_dict()
    
    # Extract destination IDs from array format
    destination_ids = request.form.getlist('destination_ids[]') if request.form else data.get('destination_ids', [])

    routingrule = repos['RoutingRule'].get(id=routingrule_id)
    if routingrule is None:
        current_app.logger.warning("Route [routes.editRoutingRule] routing rule not found (id=%s)", routingrule_id)
        return abort(404)

    # Update rule fields
    updatable = {'client_id', 'topic_id', 'device_id', 'parser_id', 'parser_config', 'active', 'priority', 'conditions'}
    update_dict = {k: v for k, v in data.items() if k in updatable}
    
    # Handle boolean conversion
    if 'active' in update_dict:
        update_dict['active'] = update_dict['active'].lower() in ['true', '1', 'on'] if isinstance(update_dict['active'], str) else bool(update_dict['active'])
    
    # Handle priority as integer
    if 'priority' in update_dict:
        update_dict['priority'] = int(update_dict['priority'])
    
    repos['RoutingRule'].update(routingrule, **update_dict)

    # Update route deposits - delete old, create new
    old_deposits = repos['RouteDeposit'].list(rule_id=routingrule.id)
    for deposit in old_deposits:
        repos['RouteDeposit'].delete(deposit)
    
    for dest_id in destination_ids:
        deposit = RouteDeposit(
            rule_id=routingrule.id,
            destination_id=int(dest_id),
            created_at=datetime.utcnow()
        )
        repos['RouteDeposit'].create(deposit)
    
    current_app.logger.info("Route [routes.editRoutingRule] routing rule updated (id=%s)", routingrule_id)
    return jsonify(status="updated", data=routingrule.to_dict())


@bp.route('/route/<string:routingrule_id>', methods=["DELETE"])
@login_required
def deleteRoutingRule(routingrule_id):
    current_app.logger.debug("Route [routes.deleteRoutingRule] called (routingrule_id=%s)", routingrule_id)
    routingrule = repos['RoutingRule'].get(id=routingrule_id)
    if routingrule is None:
        current_app.logger.warning("Route [routes.deleteRoutingRule] routing rule not found (id=%s)", routingrule_id)
        return abort(404)

    rule_dict = routingrule.to_dict()
    repos['RoutingRule'].delete(routingrule)
    current_app.logger.info("Route [routes.deleteRoutingRule] routing rule deleted (id=%s)", routingrule_id)
    return jsonify(status="deleted", data=rule_dict)