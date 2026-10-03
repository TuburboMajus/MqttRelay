from flask import current_app, render_template, request, redirect, url_for, abort, session, g, Blueprint, jsonify
from flask_login import login_required, current_user

from core.repository import repos
from core.pagination import paginate
from core.models import Client, MqttMessage, ClientDestination, Device, CryptoConfig, CryptoKey
from core.crypto import crypto_config_encrypt, get_key_bytes

from datetime import datetime, date
from pathlib import Path

import traceback
import json


clients_blueprint = Blueprint('clients', __name__)


def setup(config=None):
    """Setup blueprint with configuration."""
    return clients_blueprint


@clients_blueprint.route('/clients', methods=['GET'])
@login_required
def listClients():
	"""List all clients with pagination."""
	current_app.logger.debug(
		"Route [clients.listClients] called (json=%s, page=%s)",
		request.args.get('json'),
		request.args.get('page')
	)
	
	page = request.args.get('page', 1, type=int)
	per_page = request.args.get('per_page', 100, type=int)
	search_name = request.args.get('name', '', type=str)
	
	# Paginate results
	pagination = paginate(repos['Client'], page=page, per_page=per_page)
	
	# Filter by name if provided (simple string matching)
	if search_name:
		pagination.items = [
			client for client in pagination.items
			if search_name.lower() in client.name.lower()
		]
	
	if request.args.get('json', 'false').lower() in ["1", "true"]:
		return jsonify(pagination.to_dict())
	
	return render_template(
		f"{g.get('language', {}).get('code', 'en')}/clients/list.html",
		pagination=pagination
	)


@clients_blueprint.route('/client', methods=['GET'])
@login_required
def newClient():
	"""Serve new client form."""
	current_app.logger.debug("Route [clients.newClient] serving new client form")
	
	# Find unused client slugs from MQTT messages
	mqtt_messages = repos['MqttMessage'].list()
	client_ids = list(set([m.client for m in mqtt_messages]))
	
	unused = []
	for client_id in client_ids:
		if repos['Client'].get(slug=client_id) is None:
			unused.append(client_id)
	
	return render_template(
		f"{g.get('language', {}).get('code', 'en')}/clients/new.html",
		unused_slugs=unused
	)


@clients_blueprint.route('/client', methods=['POST'])
@login_required
def createClient():
	"""Create a new client."""
	current_app.logger.debug("Route [clients.createClient] creating client")
	
	try:
		data = request.form.to_dict() if request.form else request.get_json()
		
		client = Client(
			slug=data.get('slug'),
			name=data.get('name'),
			contact_email=data.get('contact_email'),
			phone=data.get('phone'),
			status=data.get('status', 'active'),
			created_at=datetime.utcnow()
		)
		
		repos['Client'].create(client)
		current_app.logger.info("Route [clients.createClient] client created (id=%s)", client.id)
		return redirect(url_for("clients.listClients"))
	except Exception as e:
		current_app.logger.exception("Route [clients.createClient] error creating client")
		return redirect(url_for("clients.newClient", error=str(e)))


@clients_blueprint.route('/client/<int:client_id>')
@login_required
def viewClient(client_id):
	"""View client details."""
	current_app.logger.debug("Route [clients.viewClient] called (client_id=%s)", client_id)
	
	client = repos['Client'].get(id=client_id)
	if client is None:
		current_app.logger.warning("Route [clients.viewClient] client not found (id=%s)", client_id)
		return abort(404)

	# Calculate client statistics
	client_stats = {"devices": {}}
	
	# Latest message for this client
	latest_messages = repos['MqttMessage'].list(
		orderby="at DESC",
		limit=1,
		client=client.slug
	)
	client_stats['latest_message'] = (
		latest_messages[0].at if latest_messages else None
	)
	
	# Total messages
	client_stats['total_messages'] = repos['MqttMessage'].count(client=client.slug)

	# Device statistics
	devices = repos['Device'].list(client_id=client_id)
	for device in devices:
		if device.topic:
			# Latest message for device
			device_messages = repos['MqttMessage'].list(
				topic=device.topic,
				orderby="at DESC",
				limit=1
			)
			client_stats['devices'][device.id] = {
				"last_message": device_messages[0].at if device_messages else None
			}

			# Calculate availability
			first_message = repos['MqttMessage'].list(
				client=client.slug,
				orderby="at ASC",
				limit=1
			)
			if first_message:
				first_at = first_message[0].at
				# Theoretical output based on emission rate
				if hasattr(device, 'emission_rate') and device.emission_rate:
					theoretical_output = (
						(datetime.utcnow() - first_at).total_seconds() /
						(device.emission_rate / 1000)
					)
					actual_count = repos['MqttMessage'].count(topic=device.topic)
					client_stats['devices'][device.id]['availability'] = (
						100 * actual_count / theoretical_output
						if theoretical_output > 0 else 0
					)
				else:
					client_stats['devices'][device.id]['availability'] = 0
			else:
				client_stats['devices'][device.id]['availability'] = 0

	# Calculate overall availability
	if client_stats['devices']:
		avg_availability = sum(
			d['availability'] for d in client_stats['devices'].values()
		) / len(client_stats['devices'])
		client_stats['availability'] = avg_availability
	else:
		client_stats['availability'] = 0

	destinations = repos['ClientDestination'].list(client_id=client_id)

	return render_template(
		f"{g.get('language', {}).get('code', 'en')}/clients/view.html",
		client=client,
		client_stats=client_stats,
		devices=devices,
		destinations=destinations
	)



@clients_blueprint.route('/client/<int:client_id>', methods=["PUT", "PATCH"])
@login_required
def editClient(client_id):
    current_app.logger.debug("Route [clients.editClient] called (client_id=%s)", client_id)
    client = repos['Client'].get(id=client_id)
    if client is None:
        current_app.logger.warning("Route [clients.editClient] client not found (id=%s)", client_id)
        return abort(404)

    try:
        data = request.form.to_dict() if request.form else request.get_json()
        updates = {k: v for k, v in data.items() if k in ['slug', 'name', 'contact_email', 'phone', 'status']}
        
        repos['Client'].update(client, **updates)
        current_app.logger.info("Route [clients.editClient] client updated (id=%s)", client_id)
        return jsonify({"status": "updated", "data": client.to_dict()})
    except Exception as e:
        current_app.logger.exception("Route [clients.editClient] error: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 500


@clients_blueprint.route('/client/<int:client_id>', methods=["DELETE"])
@login_required
def deleteClient(client_id):
    current_app.logger.debug("Route [clients.deleteClient] called (client_id=%s)", client_id)
    client = repos['Client'].get(id=client_id)
    if client is None:
        current_app.logger.warning("Route [clients.deleteClient] client not found (id=%s)", client_id)
        return abort(404)

    try:
        repos['Client'].delete(client)
        current_app.logger.info("Route [clients.deleteClient] client deleted (id=%s)", client_id)
        return jsonify({"status": "deleted", "data": client.to_dict()})
    except Exception as e:
        current_app.logger.exception("Route [clients.deleteClient] error: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 500



@clients_blueprint.route('/client/<int:client_id>/device/<int:device_id>', methods=["GET"])
@login_required
def getDevice(client_id, device_id):
    current_app.logger.debug("Route [clients.getDevice] called (client_id=%s, device_id=%s)", client_id, device_id)
    device = repos['Device'].get(id=device_id)
    if device is None or device.client_id != client_id:
        current_app.logger.warning("Route [clients.getDevice] device not found (client_id=%s, device_id=%s)", client_id, device_id)
        return abort(404)

    return jsonify(device.to_dict())


@clients_blueprint.route('/client/<int:client_id>/device', methods=["POST"])
@login_required
def addDevice(client_id):
    current_app.logger.debug("Route [clients.addDevice] called (client_id=%s)", client_id)
    client = repos['Client'].get(id=client_id)
    if client is None:
        current_app.logger.warning("Route [clients.addDevice] client not found (id=%s)", client_id)
        return abort(404)

    try:
        data = request.form.to_dict() if request.form else request.get_json()
        data.pop('client_id', None)
        
        device = Device(
            client_id=client_id,
            name=data.get('name'),
            device_type_id=int(data['device_type_id']),
            topic=data.get('topic'),
            external_ref=data.get('external_ref'),
            description=data.get('description'),
            location=data.get('location'),
            metadata_json=data.get('metadata_json'),
            active=data.get('active', 'true').lower() in ['true', '1', 'on'] if isinstance(data.get('active', 'true'), str) else bool(data.get('active')),
            status=data.get('status', 'unknown'),
            emission_rate=int(data['emission_rate']) if data.get('emission_rate') else None,
            created_at=datetime.utcnow()
        )
        repos['Device'].create(device)
        current_app.logger.info("Route [clients.addDevice] device created (id=%s, client_id=%s)", device.id, client_id)
        return jsonify({"status": "created", "data": device.to_dict()})
    except Exception as e:
        current_app.logger.exception("Route [clients.addDevice] error: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 500



@clients_blueprint.route('/client/<int:client_id>/device/<int:device_id>', methods=["PUT", "PATCH"])
@login_required
def editDevice(client_id, device_id):
    current_app.logger.debug("Route [clients.editDevice] called (client_id=%s, device_id=%s)", client_id, device_id)
    device = repos['Device'].get(id=device_id)
    if device is None or device.client_id != client_id:
        current_app.logger.warning("Route [clients.editDevice] device not found (client_id=%s, device_id=%s)", client_id, device_id)
        return abort(404)

    try:
        data = request.form.to_dict() if request.form else request.get_json()
        updates = {}
        for field in ['name', 'device_type_id', 'topic', 'external_ref', 'description', 'location', 'metadata_json', 'status', 'emission_rate']:
            if field in data:
                updates[field] = int(data[field]) if field in ('device_type_id', 'emission_rate') and data[field] is not None else data[field]
        if 'active' in data:
            updates['active'] = data['active'].lower() in ['true', '1', 'on'] if isinstance(data['active'], str) else bool(data['active'])
        
        repos['Device'].update(device, **updates)
        current_app.logger.info("Route [clients.editDevice] device updated (id=%s)", device_id)
        return jsonify({"status": "updated", "data": device.to_dict()})
    except Exception as e:
        current_app.logger.exception("Route [clients.editDevice] error: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 500


@clients_blueprint.route('/client/<int:client_id>/device/<int:device_id>', methods=["DELETE"])
@login_required
def deleteDevice(client_id, device_id):
    current_app.logger.debug("Route [clients.deleteDevice] called (client_id=%s, device_id=%s)", client_id, device_id)
    device = repos['Device'].get(id=device_id)
    if device is None or device.client_id != client_id:
        current_app.logger.warning("Route [clients.deleteDevice] device not found (client_id=%s, device_id=%s)", client_id, device_id)
        return abort(404)

    try:
        repos['Device'].delete(device)
        current_app.logger.info("Route [clients.deleteDevice] device deleted (id=%s)", device_id)
        return jsonify({"status": "deleted", "data": device.to_dict()})
    except Exception as e:
        current_app.logger.exception("Route [clients.deleteDevice] error: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 500


@clients_blueprint.route('/client/<int:client_id>/destination/<int:destination_id>', methods=["GET"])
@login_required
def getDestination(client_id, destination_id):
    current_app.logger.debug("Route [clients.getDestination] called (client_id=%s, destination_id=%s)", client_id, destination_id)
    destination = repos['ClientDestination'].get(id=destination_id)
    if destination is None or destination.client_id != client_id:
        current_app.logger.warning("Route [clients.getDestination] destination not found (client_id=%s, destination_id=%s)", client_id, destination_id)
        return abort(404)

    return jsonify(destination.to_dict())


@clients_blueprint.route('/client/<int:client_id>/destination', methods=["POST"])
@login_required
def addDestination(client_id):
    current_app.logger.debug("Route [clients.addDestination] called (client_id=%s)", client_id)
    client = repos['Client'].get(id=client_id)
    if client is None:
        current_app.logger.warning("Route [clients.addDestination] client not found (id=%s)", client_id)
        return abort(404)

    try:
        data = request.form.to_dict() if request.form else request.get_json()
        data.pop('client_id', None)
        
        # Handle options_json
        options_json = data.get('options_json')
        if options_json:
            if not isinstance(options_json, str):
                options_json = json.dumps(options_json)
            if options_json.strip() == '':
                options_json = None
        
        # Get crypto config for password encryption
        cc = repos['CryptoConfig'].list()
        if not cc:
            current_app.logger.error("Route [clients.addDestination] no crypto config defined")
            return jsonify({"status": "error", "error": "No secret crypto defined"}), 500
        
        cc = cc[0]
        # Decrypt password if provided
        password_encrypted = None
        if data.get('password'):
            key = get_key_bytes(cc.key_source, cc.key_id)
            password_encrypted = crypto_config_encrypt(cc, data['password'], key).encode('ascii')
        
        destination = ClientDestination(
            client_id=client_id,
            type=data.get('type'),
            host=data.get('host'),
            port=int(data.get('port')) if data.get('port') else None,
            database_name=data.get('database_name'),
            username=data.get('username'),
            password_enc=password_encrypted,
            uri=data.get('uri'),
            options_json=options_json,
            active=data.get('active', 'true').lower() in ['true', '1', 'on'] if isinstance(data.get('active', 'true'), str) else bool(data.get('active')),
            created_at=datetime.utcnow()
        )
        repos['ClientDestination'].create(destination)
        current_app.logger.info("Route [clients.addDestination] destination created (id=%s, client_id=%s)", destination.id, client_id)
        return jsonify({"status": "created", "data": destination.to_dict()})
    except Exception as e:
        current_app.logger.exception("Route [clients.addDestination] error: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 500



@clients_blueprint.route('/client/<int:client_id>/destination/<int:destination_id>', methods=["PUT", "PATCH"])
@login_required
def editDestination(client_id, destination_id):
    current_app.logger.debug("Route [clients.editDestination] called (client_id=%s, destination_id=%s)", client_id, destination_id)
    destination = repos['ClientDestination'].get(id=destination_id)
    if destination is None or destination.client_id != client_id:
        current_app.logger.warning("Route [clients.editDestination] destination not found (client_id=%s, destination_id=%s)", client_id, destination_id)
        return abort(404)

    try:
        data = request.form.to_dict() if request.form else request.get_json()
        
        # Get crypto config
        cc = repos['CryptoConfig'].list()
        if not cc:
            current_app.logger.error("Route [clients.editDestination] no crypto config defined")
            return jsonify({"status": "error", "error": "No secret crypto defined"}), 500
        
        cc = cc[0]
        
        updates = {}
        for field in ['type', 'host', 'port', 'database_name', 'username', 'uri', 'options_json', 'active']:
            if field in data:
                if field == 'port':
                    updates[field] = int(data[field]) if data[field] else None
                elif field == 'active':
                    updates[field] = data[field].lower() in ['true', '1', 'on'] if isinstance(data[field], str) else bool(data[field])
                else:
                    updates[field] = data[field]
        
        # Handle password encryption if provided
        if data.get('password') and str(data['password']).strip():
            key = get_key_bytes(cc.key_source, cc.key_id)
            updates['password_enc'] = crypto_config_encrypt(cc, str(data['password']), key).encode('ascii')
        
        repos['ClientDestination'].update(destination, **updates)
        current_app.logger.info("Route [clients.editDestination] destination updated (id=%s)", destination_id)
        return jsonify({"status": "updated", "data": destination.to_dict()})
    except Exception as e:
        current_app.logger.exception("Route [clients.editDestination] error: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 500


@clients_blueprint.route('/client/<int:client_id>/destination/<int:destination_id>', methods=["DELETE"])
@login_required
def deleteDestination(client_id, destination_id):
    current_app.logger.debug("Route [clients.deleteDestination] called (client_id=%s, destination_id=%s)", client_id, destination_id)
    destination = repos['ClientDestination'].get(id=destination_id)
    if destination is None or destination.client_id != client_id:
        current_app.logger.warning("Route [clients.deleteDestination] destination not found (client_id=%s, destination_id=%s)", client_id, destination_id)
        return abort(404)

    try:
        repos['ClientDestination'].delete(destination)
        current_app.logger.info("Route [clients.deleteDestination] destination deleted (id=%s)", destination_id)
        return jsonify({"status": "deleted", "data": destination.to_dict()})
    except Exception as e:
        current_app.logger.exception("Route [clients.deleteDestination] error: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 500