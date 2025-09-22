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


destinations_blueprint = MultiLanguageBlueprint('destinations',__name__, load_in_g=True, default_config={
	"templates_folder":"{language}/destinations",
	"destinations_per_page":100,
}, dictionnary_selector=lambda lg:lg['code'])


@destinations_blueprint.route('/client_destinations')
@login_required
@Paginator(destinations_blueprint, page_size_config="destinations_per_page").for_entity(ClientDestination).with_default_filter(True).paginate
@destinations_blueprint.with_dictionnary
def listDestinations(pagination):
	if request.args.get('json','false').lower() in ["1","true"]:
		return pagination.to_dict()['current']
	return AuthenticatedUserTemplate(
		Path(destinations_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("list.html"),
		pagination=pagination
	).handles_success_and_error().with_dictionnary().with_sidebar("destinations").render()


@destinations_blueprint.route('/client_destination')
@login_required
@destinations_blueprint.with_dictionnary
def newDestination():
	return AuthenticatedUserTemplate(
		Path(destinations_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("new.html"),
	).handles_success_and_error().with_dictionnary().with_sidebar("destinations").render()


@destinations_blueprint.route('/client_destination',methods=["POST"])
@login_required
@body_content('form')
def createDestination(form):
	for field in ["capabilities","payload_schema","defaults_json"]:
		if form.get(field,"") is not None and form.get(field,'').strip() == "":
			form[field] = None
	destination = Destination(id=-1, created_at=datetime.now(),**form)
	Destination.storage.create(destination)
	return redirect(url_for("destinations.listDestinations"))


@destinations_blueprint.route('/client_destination/<int:destination_id>')
@login_required
@destinations_blueprint.with_dictionnary
def viewDestination(destination_id):
	destination = ClientDestination.storage.get(id=destination_id)
	if destination is None:
		return abort(404)

	return AuthenticatedUserTemplate(
		Path(destinations_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("view.html"),
		destination=destination
	).handles_success_and_error().with_dictionnary().with_sidebar("destinations").render()


@destinations_blueprint.route('/client_destination/<int:destination_id>/example')
@login_required
@destinations_blueprint.with_dictionnary
def viewExampleData(destination_id):
	destination = ClientDestination.storage.get(id=destination_id)
	if destination is None:
		return abort(404)

	examples = list(Destination.storage.list(Not(Equals(StringAttribute("topic"))),destination_type_id=destination['id']))
	for example in examples:
		message = MqttMessage.storage.get(topic=example['topic'])
		if message is not None:
			return message['payload']
	return {}