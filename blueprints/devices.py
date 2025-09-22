from flask import current_app, render_template, request, redirect, url_for, abort, session,g
from flask_login import LoginManager, login_required, current_user

from temod_flask.utils.content_readers import body_content
from temod_flask.blueprint import MultiLanguageBlueprint
from temod_flask.blueprint.utils import Paginator

from temod.base.attribute import *
from temod.base.condition import *

from front.renderers.users import AuthenticatedUserTemplate

from datetime import datetime, date
from pathlib import Path

import traceback
import json


devices_blueprint = MultiLanguageBlueprint('devices',__name__, load_in_g=True, default_config={
	"templates_folder":"{language}/devices",
	"devices_per_page":100,
}, dictionnary_selector=lambda lg:lg['code'])


@devices_blueprint.route('/devices')
@login_required
@Paginator(devices_blueprint, page_size_config="devices_per_page").for_entity(DeviceType).with_default_filter(True).paginate
@devices_blueprint.with_dictionnary
def listDevices(pagination):
	if request.args.get('json','false').lower() in ["1","true"]:
		return pagination.to_dict()['current']
	return AuthenticatedUserTemplate(
		Path(devices_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("list.html"),
		pagination=pagination
	).handles_success_and_error().with_dictionnary().with_sidebar("devices").render()


@devices_blueprint.route('/device')
@login_required
@devices_blueprint.with_dictionnary
def newDevice():
	return AuthenticatedUserTemplate(
		Path(devices_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("new.html"),
	).handles_success_and_error().with_dictionnary().with_sidebar("devices").render()


@devices_blueprint.route('/device',methods=["POST"])
@login_required
@body_content('form')
def createDevice(form):
	for field in ["capabilities","payload_schema","defaults_json"]:
		if form.get(field,"") is not None and form.get(field,'').strip() == "":
			form[field] = None
	device = Device(id=-1, created_at=datetime.now(),**form)
	Device.storage.create(device)
	return redirect(url_for("devices.listDevices"))


@devices_blueprint.route('/device/<int:device_id>')
@login_required
@devices_blueprint.with_dictionnary
def viewDevice(device_id):
	device = DeviceType.storage.get(id=device_id)
	if device is None:
		return abort(404)

	return AuthenticatedUserTemplate(
		Path(devices_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("view.html"),
		device=device
	).handles_success_and_error().with_dictionnary().with_sidebar("devices").render()


@devices_blueprint.route('/device/<int:device_id>/example')
@login_required
@devices_blueprint.with_dictionnary
def viewExampleData(device_id):
	device = DeviceType.storage.get(id=device_id)
	if device is None:
		return abort(404)

	examples = list(Device.storage.list(Not(Equals(StringAttribute("topic"))),device_type_id=device['id']))
	for example in examples:
		message = MqttMessage.storage.get(topic=example['topic'])
		if message is not None:
			return message['payload']
	return {}


@devices_blueprint.route('/device/unique')
@login_required
@devices_blueprint.with_dictionnary
def checkUnique():
	vendor = (request.args.get("vendor") or "").strip()
	model = (request.args.get("model") or "").strip()
	if not vendor or not model:
		return {"unique": False}
	exists = DeviceType.storage.get(vendor=vendor, model=model) is not None
	return {"unique": not exists}