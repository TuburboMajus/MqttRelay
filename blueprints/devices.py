from flask import current_app, render_template, request, redirect, url_for, abort, session, g, jsonify, Blueprint
from flask_login import login_required, current_user

from core.repository import repos
from core.pagination import paginate
from core.models import DeviceType, Device, MqttMessage
from core.validation import clean_json_field

from datetime import datetime, date
import logging


bp = Blueprint('devices', __name__)

def setup(config=None):
    """Setup devices blueprint with configuration."""
    return bp


@bp.route('/devices')
@login_required
def listDevices():
    current_app.logger.debug("Route [devices.listDevices] called (json=%s, page=%s)", request.args.get('json'), request.args.get('page'))
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    pagination = paginate(repos['DeviceType'], page=page, per_page=per_page)
    
    if request.args.get('json', 'false').lower() in ["1", "true"]:
        return jsonify(pagination.to_dict())
    
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/devices/list.html",
        pagination=pagination
    )


@bp.route('/device')
@login_required
def newDevice():
    current_app.logger.debug("Route [devices.newDevice] serving new device form")
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/devices/new.html"
    )


@bp.route('/device', methods=["POST"])
@login_required
def createDevice():
    current_app.logger.debug("Route [devices.createDevice] creating device type")
    data = request.form.to_dict() if request.form else request.get_json()
    
    try:
        capabilities = clean_json_field(data.get('capabilities'), 'capabilities')
        payload_schema = clean_json_field(data.get('payload_schema'), 'payload_schema')
        defaults_json = clean_json_field(data.get('defaults_json'), 'defaults_json')
    except ValueError as e:
        current_app.logger.warning("Route [devices.createDevice] validation error: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 400
    
    device = DeviceType(
        vendor=data.get('vendor'),
        model=data.get('model'),
        kind=data.get('kind'),
        capabilities=capabilities,
        payload_schema=payload_schema,
        defaults_json=defaults_json,
        created_at=datetime.utcnow()
    )
    repos['DeviceType'].create(device)
    current_app.logger.info("Route [devices.createDevice] device type created (id=%s)", device.id)
    return redirect(url_for("devices.listDevices"))


@bp.route('/device/<int:device_id>')
@login_required
def viewDevice(device_id):
    current_app.logger.debug("Route [devices.viewDevice] called (device_id=%s)", device_id)
    device = repos['DeviceType'].get(id=device_id)
    if device is None:
        current_app.logger.warning("Route [devices.viewDevice] device not found (id=%s)", device_id)
        return abort(404)

    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/devices/view.html",
        device=device
    )


@bp.route('/device/<int:device_id>/example')
@login_required
def viewExampleData(device_id):
    current_app.logger.debug("Route [devices.viewExampleData] called (device_id=%s)", device_id)
    device = repos['DeviceType'].get(id=device_id)
    if device is None:
        current_app.logger.warning("Route [devices.viewExampleData] device not found (id=%s)", device_id)
        return abort(404)

    # Find devices of this type that have a topic
    examples = repos['Device'].list(device_type_id=device.id)
    for example in examples:
        if example.topic:  # Skip if no topic assigned
            message = repos['MqttMessage'].get(topic=example.topic)
            if message is not None:
                current_app.logger.info("Route [devices.viewExampleData] example payload found (device_id=%s)", device_id)
                return message.payload if hasattr(message, 'payload') else {}
    
    return {}


@bp.route('/device/unique')
@login_required
def checkUnique():
    vendor = (request.args.get("vendor") or "").strip()
    model = (request.args.get("model") or "").strip()
    current_app.logger.debug("Route [devices.checkUnique] called (vendor=%s, model=%s)", vendor, model)
    
    if not vendor or not model:
        return jsonify(unique=False)
    
    exists = repos['DeviceType'].get(vendor=vendor, model=model) is not None
    return jsonify(unique=not exists)