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


users_blueprint = MultiLanguageBlueprint('users',__name__, load_in_g=True, default_config={
	"templates_folder":"{language}/users",
	"users_per_page":100,
}, dictionnary_selector=lambda lg:lg['code'])


@users_blueprint.route('/users')
@login_required
@Paginator(users_blueprint, page_size_config="users_per_page").for_entity(User).with_default_filter(True).paginate
@users_blueprint.with_dictionnary
def listUsers(pagination):
	if request.args.get('json','false').lower() in ["1","true"]:
		return pagination.to_dict()['current']
	return AuthenticatedUserTemplate(
		Path(users_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("list.html"),
		pagination=pagination
	).handles_success_and_error().with_dictionnary().with_sidebar("users").render()


@users_blueprint.route('/user')
@login_required
@users_blueprint.with_dictionnary
def newUser():
	return AuthenticatedUserTemplate(
		Path(users_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("new.html"),
	).handles_success_and_error().with_dictionnary().with_sidebar("users").render()


@users_blueprint.route('/user',methods=["POST"])
@login_required
@body_content('form')
def createUser(form):
	for field in ["capabilities","payload_schema","defaults_json"]:
		if form.get(field,"") is not None and form.get(field,'').strip() == "":
			form[field] = None
	user = User(id=-1, created_at=datetime.now(),**form)
	User.storage.create(user)
	return redirect(url_for("users.listUsers"))


@users_blueprint.route('/user/<string:user_id>')
@login_required
@users_blueprint.with_dictionnary
def viewUser(user_id):
	user = User.storage.get(id=user_id)
	if user is None:
		return abort(404)

	return AuthenticatedUserTemplate(
		Path(users_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("view.html"),
		user=user
	).handles_success_and_error().with_dictionnary().with_sidebar("users").render()


@users_blueprint.route('/user/<string:user_id>', methods=["PUT", "PATCH"])
@login_required
@body_content('json')
def editUser(form, user_id):
    user = User.storage.get(id=user_id)
    if user is None:
        return abort(404)

    user.takeSnapshot().setAttributes(
        **{field: form.get(field, user[field]) for field in User.UPDATABLE_FIELDS}
    )
    User.storage.updateOnSnapshot(user)
    return {"status":"updated", "data":user.to_dict()}


@users_blueprint.route('/user/<string:user_id>/password', methods=["PUT", "PATCH"])
@login_required
@body_content('json')
def changePassword(form, user_id):
	user = User.storage.get(id=userid)

	if user is None:
		return Response(status=404)

	if user['id'] != current_user['id']:
		return Response(status=404)
		
	if user.attributes['password'] != form['password']:
		return {"status":"error", "data":g.dictionnary['profile']['wrong_password']}

	if form['npassword'] != form['cpassword']:
		return {"status":"error", "data":g.dictionnary['profile']['unmatched_passwords']}

	if len(form['npassword']) < 8:
		return {"status":"error", "data":g.dictionnary['profile']['invalid_password']}

	user.takeSnapshot()
	user['password'] = form['npassword']

	User.storage.updateOnSnapshot(user)
	return {"status":"updated", "data":user.to_dict()}


@users_blueprint.route('/user/<string:user_id>', methods=["DELETE"])
@login_required
def deleteUser(user_id):
    user = User.storage.get(id=user_id)
    if user is None:
        return abort(404)

    User.storage.delete(user)
    return {"status":"deleted", "data":user.to_dict()}