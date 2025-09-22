from flask import current_app, render_template, request, redirect, url_for, abort, session,g
from flask_login import LoginManager, login_required, current_user

from temod_flask.utils.content_readers import body_content
from temod_flask.blueprint import MultiLanguageBlueprint
from temod_flask.blueprint.utils import Paginator

from front.renderers.users import AuthenticatedUserTemplate

from datetime import datetime, date
from pathlib import Path

import traceback
import json


routes_blueprint = MultiLanguageBlueprint('routes',__name__, load_in_g=True, default_config={
	"templates_folder":"{language}/routes",
	"routingrules_per_page":100,
}, dictionnary_selector=lambda lg:lg['code'])


@routes_blueprint.route('/routes')
@login_required
@Paginator(routes_blueprint, page_size_config="routingrules_per_page").for_entity(RoutingRuleFile).with_default_filter(True).paginate
@routes_blueprint.with_dictionnary
def listRoutingRules(pagination):
	if request.args.get('json','false').lower() in ["1","true"]:
		return pagination.to_dict()['current']
	print(pagination.current)
	return AuthenticatedUserTemplate(
		Path(routes_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("list.html"),
		pagination=pagination
	).handles_success_and_error().with_dictionnary().with_sidebar("routes").render()


@routes_blueprint.route('/route')
@login_required
@routes_blueprint.with_dictionnary
def newRoutingRule():
	return AuthenticatedUserTemplate(
		Path(routes_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("new.html"),
		parsers=list(Parser.storage.list())
	).handles_success_and_error().with_dictionnary().with_sidebar("routes").render()


@routes_blueprint.route('/route',methods=["POST"])
@login_required
@body_content('form')
def createRoutingRule(form):
	destinations = form.pop("destination_ids[]",[])
	deposits = []

	for field in ['device_id','conditions']:
		if form.get('field','').strip() == '':
			form[field] = None

	routingrule = RoutingRule(id=RoutingRule.storage.generate_value('id'),created_at=datetime.now(),active=form.pop('active','on').lower() in ["on","1"],**form)
	for destination in destinations:
		deposits.append(RouteDeposit(rule_id=routingrule['id'], destination_id=int(destination)))

	RoutingRule.storage.create(routingrule)
	for deposit in deposits:
		RouteDeposit.storage.create(deposit)
	return redirect(url_for("routes.listRoutingRules"))


@routes_blueprint.route('/route/<string:routingrule_id>')
@login_required
@routes_blueprint.with_dictionnary
def viewRoutingRule(routingrule_id):
	routingrule = RoutingRule.storage.get(id=routingrule_id)
	if routingrule is None:
		return abort(404)

	return AuthenticatedUserTemplate(
		Path(routes_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("view.html"),
		rule=routingrule, destinations=list(RouteDepositDetails.storage.list(rule_id=routingrule['id']))
	).handles_success_and_error().with_dictionnary().with_sidebar("routes").render()



@routes_blueprint.route('/route/<string:routingrule_id>', methods=["PUT", "PATCH"])
@login_required
@body_content('json')
def editRoutingRule(form, routingrule_id):
	destinations = form.pop("destination_ids",[])
	deposits = []

	routingrule = RoutingRule.storage.get(id=routingrule_id)
	if routingrule is None:
		return abort(404)

	for destination in destinations:
		deposits.append(RouteDeposit(rule_id=routingrule['id'], destination_id=int(destination)))

	routingrule.takeSnapshot().setAttributes(
		**{field: form.get(field, routingrule[field]) for field in RoutingRule.UPDATABLE_FIELDS}
	)
	RoutingRule.storage.updateOnSnapshot(routingrule)

	RouteDeposit.storage.delete(rule_id=routingrule['id'],many=True)
	for deposit in deposits:
		RouteDeposit.storage.create(deposit)
	
	return {"status":"updated", "data":routingrule.to_dict()}


@routes_blueprint.route('/route/<string:routingrule_id>', methods=["DELETE"])
@login_required
def deleteRoutingRule(routingrule_id):
	routingrule = RoutingRule.storage.get(id=routingrule_id)
	if routingrule is None:
		return abort(404)

	RoutingRule.storage.delete(routingrule)
	return {"status":"deleted", "data":routingrule.to_dict()}