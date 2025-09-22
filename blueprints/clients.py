from flask import current_app, render_template, request, redirect, url_for, abort, session,g
from flask_login import LoginManager, login_required, current_user

from temod_flask.utils.content_readers import body_content
from temod_flask.blueprint import MultiLanguageBlueprint
from temod_flask.blueprint.utils import Paginator

from front.renderers.users import AuthenticatedUserTemplate

from temod.base.attribute import *
from temod.base.condition import *

from datetime import datetime, date
from pathlib import Path

import traceback
import json


clients_blueprint = MultiLanguageBlueprint('clients',__name__, load_in_g=True, default_config={
	"templates_folder":"{language}/clients",
	"clients_per_page":100,
}, dictionnary_selector=lambda lg:lg['code'])


@clients_blueprint.route('/clients')
@login_required
@Paginator(clients_blueprint, page_size_config="clients_per_page").for_entity(Client).with_filter(lambda x: Contains(StringAttribute("name",value=x.get('name','')))).with_default_filter(False).paginate
@clients_blueprint.with_dictionnary
def listClients(pagination):
	if request.args.get('json','false').lower() in ["1","true"]:
		return pagination.to_dict()['current']
	return AuthenticatedUserTemplate(
		Path(clients_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("list.html"),
		pagination=pagination
	).handles_success_and_error().with_dictionnary().with_sidebar("clients").render()


@clients_blueprint.route('/client')
@login_required
@clients_blueprint.with_dictionnary
def newClient():
	mqtt_messages = list(MqttMessage.storage.list())
	client_ids = list(set([m['client'] for m in mqtt_messages]))
	unused = []
	for client_id in client_ids:
		if Client.storage.get(slug=client_id) is None:
			unused.append(client_id)
	return AuthenticatedUserTemplate(
		Path(clients_blueprint.configuration["templates_folder"].format(
				language=g.language['code'])
		).joinpath("new.html"),
		unused_slugs=unused
	).handles_success_and_error().with_dictionnary().with_sidebar("clients").render()


@clients_blueprint.route('/client',methods=["POST"])
@login_required
@body_content('form')
def createClient(form):
	client = Client(
		id=-1, created_at=datetime.now(),**form
	)
	Client.storage.create(client)
	return redirect(url_for("clients.listClients"))


@clients_blueprint.route('/client/<int:client_id>')
@login_required
@clients_blueprint.with_dictionnary
def viewClient(client_id):
	client = Client.storage.get(id=client_id)
	if client is None:
		return abort(404)

	client_stats = {"devices":{}}
	lastest_message = list(MqttMessage.storage.list(client=client['slug'],orderby="at DESC",limit=1)) 
	client_stats['lastest_message'] = lastest_message[0]['at'] if len(lastest_message) else None
	client_stats['total_messages'] = MqttMessage.storage.count(client=client['slug'])

	devices = list(DeviceFile.storage.list(client_id=client_id))
	for device in devices:
		if device['topic'] is not None:

			messages = list(MqttMessage.storage.list(topic=device['topic'],orderby="at DESC",limit=1)) 
			client_stats['devices'][device['id']] = {"last_message":messages[0]['at'] if len(messages) else None}

			first_message = list(MqttMessage.storage.list(client=client['slug'],orderby="at ASC",limit=1))
			first_message = first_message[0] if len(first_message) else None
			if first_message is not None:
				therical_output = (datetime.now()-first_message['at']).total_seconds()/(device['emission_rate']/1000)
				client_stats['devices'][device['id']]['availability'] = 100*MqttMessage.storage.count(topic=device['topic'])/therical_output
			else:
				client_stats['devices'][device['id']]['availability'] = 0

	client_stats['availability'] = ((sum([device_stats['availability'] for device, device_stats in client_stats['devices'].items()])/len(client_stats['devices'])) if len(client_stats['devices']) else 0)

	return AuthenticatedUserTemplate(
		Path(clients_blueprint.configuration["templates_folder"].format(
				language=g.language['code'])
		).joinpath("view.html"),
		client=client,
		client_stats=client_stats,
		devices=devices,
		destinations=ClientDestination.storage.list(client_id=client_id)
	).handles_success_and_error().with_dictionnary().with_sidebar("clients").render()



@clients_blueprint.route('/client/<int:client_id>', methods=["PUT", "PATCH"])
@login_required
@body_content('json')
def editClient(form, client_id):
	client = Client.storage.get(id=client_id)
	if client is None:
		return abort(404)

	client.takeSnapshot().setAttributes(
		**{field: form.get(field, client[field]) for field in Client.UPDATABLE_FIELDS}
	)
	Client.storage.updateOnSnapshot(client)
	return {"status":"updated", "data":client.to_dict()}


@clients_blueprint.route('/client/<int:client_id>', methods=["DELETE"])
@login_required
def deleteClient(client_id):
	client = Client.storage.get(id=client_id)
	if client is None:
		return abort(404)

	Client.storage.delete(client)
	return {"status":"deleted", "data":client.to_dict()}



@clients_blueprint.route('/client/<int:client_id>/device/<int:device_id>', methods=["GET"])
@login_required
def getDevice(client_id,device_id):
	device = Device.storage.get(id=device_id)
	if device is None or device['client_id'] != client_id:
		return abort(404)

	if request.args.get('json'):
		return device.to_dict()
	return device


@clients_blueprint.route('/client/<int:client_id>/device', methods=["POST"])
@login_required
@body_content('json')
def addDevice(form, client_id):
	client = Client.storage.get(id=client_id)
	if client is None:
		return abort(404)

	assert(form.pop('client_id',None) in [None, client_id])
	device = Device(
		id=-1, client_id=client_id,created_at=datetime.now(),**form
	)
	device = Device.storage.create(device)
	return {"status":"created", "data":client.to_dict()}



@clients_blueprint.route('/client/<int:client_id>/device/<int:device_id>', methods=["PUT", "PATCH"])
@login_required
@body_content('json')
def editDevice(form,client_id,device_id):
	device = Device.storage.get(id=device_id)
	if device is None or device['client_id'] != client_id:
		return abort(404)

	device.takeSnapshot().setAttributes(
		**{field: form.get(field, device[field]) for field in Device.UPDATABLE_FIELDS}
	)
	Device.storage.updateOnSnapshot(device)
	return {"status":"updated", "data":device.to_dict()}


@clients_blueprint.route('/client/<int:client_id>/device/<int:device_id>', methods=["DELETE"])
@login_required
def deleteDevice(client_id,device_id):
	device = Device.storage.get(id=device_id)
	if device is None or device['client_id'] != client_id:
		return abort(404)

	Device.storage.delete(id=device['id'])
	return {"status":"deleted", "data":device.to_dict()}


@clients_blueprint.route('/client/<int:client_id>/destination/<int:destination_id>', methods=["GET"])
@login_required
def getDestination(client_id,destination_id):
	destination = ClientDestination.storage.get(id=destination_id)
	if destination is None or destination['client_id'] != client_id:
		return abort(404)

	if request.args.get('json'):
		return destination.to_dict()
	return destination


@clients_blueprint.route('/client/<int:client_id>/destination', methods=["POST"])
@login_required
@body_content('json')
def addDestination(form, client_id):
	client = Client.storage.get(id=client_id)
	if client is None:
		return abort(404)

	assert(form.pop('client_id',None) in [None, client_id])

	for field in ["options_json"]:

		if not(type(form[field]) is str):
			form[field] = json.dumps(form[field]) 

		if form.get(field,"") is not None and form.get(field,'').strip() == "":
			form[field] = None

	cc = CryptoConfig.storage.get()
	if cc is None:
		return {"status":"error","error":"No secret crypto defined"}

	destination = ClientDestination(
		id=-1, client_id=client_id,created_at=datetime.now(),password_enc=cc.encrypt(form['password'], CryptoKey.get_key_bytes(cc['key_source'], cc['key_id'])).encode('ascii'),**form
	)
	destination = ClientDestination.storage.create(destination)
	return {"status":"created", "data":client.to_dict()}



@clients_blueprint.route('/client/<int:client_id>/destination/<int:destination_id>', methods=["PUT", "PATCH"])
@login_required
@body_content('json')
def editDestination(form,client_id,destination_id):
	destination = ClientDestination.storage.get(id=destination_id)
	if destination is None or destination['client_id'] != client_id:
		return abort(404)

	destination.takeSnapshot()

	cc = CryptoConfig.storage.get()
	if cc is None:
		return {"status":"error","error":"No secret crypto defined"}


	if not(form.get('password','') in [None,""]):
		destination['password_enc'] = cc.encrypt(form['password'], CryptoKey.get_key_bytes(cc['key_source'], cc['key_id'])).encode('ascii')

	destination.setAttributes(
		**{field: form.get(field, destination[field]) for field in ClientDestination.UPDATABLE_FIELDS}
	)
	ClientDestination.storage.updateOnSnapshot(destination)
	return {"status":"updated", "data":destination.to_dict()}


@clients_blueprint.route('/client/<int:client_id>/destination/<int:destination_id>', methods=["DELETE"])
@login_required
def deleteDestination(client_id,destination_id):
	destination = ClientDestination.storage.get(id=destination_id)
	if destination is None or destination['client_id'] != client_id:
		return abort(404)

	ClientDestination.storage.delete(id=destination['id'])
	return {"status":"deleted", "data":destination.to_dict()}