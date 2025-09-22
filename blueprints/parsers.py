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

from context import PARSERS_DB

import traceback
import json


parsers_blueprint = MultiLanguageBlueprint('parsers',__name__, load_in_g=True, default_config={
	"templates_folder":"{language}/parsers",
	"parsers_per_page":100,
}, dictionnary_selector=lambda lg:lg['code'])


@parsers_blueprint.route('/parsers')
@login_required
@Paginator(parsers_blueprint, page_size_config="parsers_per_page").for_entity(Parser).with_filter(lambda x: Contains(StringAttribute("name",value=x.get('name','')))).with_default_filter(True).paginate
@parsers_blueprint.with_dictionnary
def listParsers(pagination):
	if request.args.get('json','false').lower() in ["1","true"]:
		return pagination.to_dict()['current']
	return AuthenticatedUserTemplate(
		Path(parsers_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("list.html"),
		pagination=pagination
	).handles_success_and_error().with_dictionnary().with_sidebar("parsers").render()


@parsers_blueprint.route('/parser')
@login_required
@parsers_blueprint.with_dictionnary
def newParser():
	return AuthenticatedUserTemplate(
		Path(parsers_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("new.html"),
	).handles_success_and_error().with_dictionnary().with_sidebar("parsers").render()


@parsers_blueprint.route('/parser',methods=["POST"])
@login_required
@body_content('form')
def createParser(form):
	for field in ["config_schema"]:
		if form.get(field,"") is not None and form.get(field,'').strip() == "":
			form[field] = None
	print(form)
	parser = Parser(id=-1,active=form.pop('active','on').lower() in ["on","1"],**form)
	Parser.storage.create(parser)
	return redirect(url_for("parsers.listParsers"))


@parsers_blueprint.route('/parser/<int:parser_id>')
@login_required
@parsers_blueprint.with_dictionnary
def viewParser(parser_id):
	parser = Parser.storage.get(id=parser_id)
	if parser is None:
		return abort(404)

	code_filename = "_".join([parser['name'].lower().replace(" ","_"), parser['version'].lower().replace('.','_')])
	try:
		code = PARSERS_DB.read(code_filename)
	except:
		code = None

	return AuthenticatedUserTemplate(
		Path(parsers_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("view.html"),
		parser=parser, code=code, metrics=list(Metric.storage.list())
	).handles_success_and_error().with_dictionnary().with_sidebar("parsers").render()



@parsers_blueprint.route('/parser/<int:parser_id>', methods=["PUT", "PATCH"])
@login_required
@body_content('json')
def editParser(form, parser_id):
    parser = Parser.storage.get(id=parser_id)
    if parser is None:
        return abort(404)

    parser.takeSnapshot().setAttributes(
        **{field: form.get(field, parser[field]) for field in Parser.UPDATABLE_FIELDS}
    )

    if form.get('code') is not None:
    	code_filename = "_".join([parser['name'].lower().replace(" ","_"), parser['version'].lower().replace('.','_')])
    	PARSERS_DB.write(code_filename, form['code'], mode="")
    	code_filename_with_suffix = f"{code_filename}.{Parser.FILE_EXTENSIONS[parser['language'].lower()].lower()}"
    	PARSERS_DB.write(code_filename_with_suffix, form['code'], mode="")

    Parser.storage.updateOnSnapshot(parser)
    return {"status":"updated", "data":parser.to_dict()}


@parsers_blueprint.route('/parser/<int:parser_id>', methods=["DELETE"])
@login_required
def deleteParser(parser_id):
    parser = Parser.storage.get(id=parser_id)
    if parser is None:
        return abort(404)

    Parser.storage.delete(parser)
    return {"status":"deleted", "data":parser.to_dict()}