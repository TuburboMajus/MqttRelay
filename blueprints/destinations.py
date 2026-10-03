from flask import current_app, render_template, request, redirect, url_for, abort, session, g, jsonify, Blueprint
from flask_login import login_required, current_user

from core.repository import repos
from core.pagination import paginate
from core.models import ClientDestination

from datetime import datetime, date
import json
import logging


bp = Blueprint('destinations', __name__)

def setup(config=None):
    """Setup destinations blueprint with configuration."""
    return bp


@bp.route('/client_destinations')
@login_required
def listDestinations():
    current_app.logger.debug("Route [destinations.listDestinations] called (json=%s, page=%s)", request.args.get('json'), request.args.get('page'))
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    pagination = paginate(repos['ClientDestination'], page=page, per_page=per_page)
    
    if request.args.get('json', 'false').lower() in ["1", "true"]:
        return jsonify(pagination.to_dict())
    
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/destinations/list.html",
        pagination=pagination
    )


@bp.route('/client_destination')
@login_required
def newDestination():
    current_app.logger.debug("Route [destinations.newDestination] serving new destination form")
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/destinations/new.html"
    )


@bp.route('/client_destination', methods=["POST"])
@login_required
def createDestination():
    current_app.logger.debug("Route [destinations.createDestination] creating destination")
    data = request.form.to_dict() if request.form else request.get_json()
    
    # Handle options_json field
    options_json = data.get('options_json', '')
    if options_json and isinstance(options_json, dict):
        options_json = json.dumps(options_json)
    elif not options_json or (isinstance(options_json, str) and options_json.strip() == ''):
        options_json = None
    
    destination = ClientDestination(
        client_id=data.get('client_id'),
        type=data.get('type'),
        host=data.get('host'),
        port=int(data.get('port', 0)) if data.get('port') else None,
        database_name=data.get('database_name'),
        username=data.get('username'),
        password_enc=data.get('password_enc'),
        uri=data.get('uri'),
        options_json=options_json,
        active=data.get('active', 'true').lower() in ['true', '1', 'on'] if isinstance(data.get('active', 'true'), str) else bool(data.get('active')),
        created_at=datetime.utcnow()
    )
    repos['ClientDestination'].create(destination)
    current_app.logger.info("Route [destinations.createDestination] destination created (id=%s)", destination.id)
    return redirect(url_for("destinations.listDestinations"))


@bp.route('/client_destination/<int:destination_id>')
@login_required
def viewDestination(destination_id):
    current_app.logger.debug("Route [destinations.viewDestination] called (destination_id=%s)", destination_id)
    destination = repos['ClientDestination'].get(id=destination_id)
    if destination is None:
        current_app.logger.warning("Route [destinations.viewDestination] destination not found (id=%s)", destination_id)
        return abort(404)

    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/destinations/view.html",
        destination=destination
    )


@bp.route('/client_destination/<int:destination_id>/example')
@login_required
def viewExampleData(destination_id):
    current_app.logger.debug("Route [destinations.viewExampleData] called (destination_id=%s)", destination_id)
    destination = repos['ClientDestination'].get(id=destination_id)
    if destination is None:
        current_app.logger.warning("Route [destinations.viewExampleData] destination not found (id=%s)", destination_id)
        return abort(404)

    options = destination.options_json
    if isinstance(options, str) and options.strip():
        try:
            return jsonify(json.loads(options))
        except Exception:
            current_app.logger.warning("Route [destinations.viewExampleData] invalid JSON options for destination (id=%s)", destination_id)
            return jsonify(options)
    return jsonify({})