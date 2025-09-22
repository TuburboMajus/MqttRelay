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


topics_blueprint = MultiLanguageBlueprint('topics',__name__, load_in_g=True, default_config={
	"templates_folder":"{language}/topics",
	"topics_per_page":100,
}, dictionnary_selector=lambda lg:lg['code'])


@topics_blueprint.route('/topics')
@login_required
@Paginator(topics_blueprint, page_size_config="topics_per_page").for_entity(MqttTopicFile).with_default_filter(True).paginate
@topics_blueprint.with_dictionnary
def listTopics(pagination):
	if request.args.get('json','false').lower() in ["1","true"]:
		return pagination.to_dict()['current']
	return AuthenticatedUserTemplate(
		Path(topics_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("list.html"),
		pagination=pagination
	).handles_success_and_error().with_dictionnary().with_sidebar("topics").render()


@topics_blueprint.route('/unlinked_topics')
@login_required
@Paginator(topics_blueprint, page_size_config="topics_per_page").for_entity(DeviceTopic).with_filter(
	lambda x:And(Equals(StringAttribute("client_id",value=x.get('client_id',0),owner_name=Device.ENTITY_NAME)),Equals(StringAttribute("topic",owner_name=MqttTopic.ENTITY_NAME)))
).with_default_filter(True).paginate
@topics_blueprint.with_dictionnary
def listUnlnkedTopics(pagination):
	if request.args.get('json','false').lower() in ["1","true"]:
		return pagination.to_dict()['current']
	return AuthenticatedUserTemplate(
		Path(topics_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("list.html"),
		pagination=pagination
	).handles_success_and_error().with_dictionnary().with_sidebar("topics").render()


@topics_blueprint.route('/topic')
@login_required
@topics_blueprint.with_dictionnary
def newTopic():
	return AuthenticatedUserTemplate(
		Path(topics_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("new.html"),
	).handles_success_and_error().with_dictionnary().with_sidebar("topics").render()


@topics_blueprint.route('/topic',methods=["POST"])
@login_required
@body_content('form')
def createTopic(form):
	topic = MqttTopic(id=-1,active=form.pop('active','on').lower() in ["on","1"],created_at=datetime.now(),**form)
	MqttTopic.storage.create(topic)
	return redirect(url_for("topics.listTopics"))


@topics_blueprint.route('/topic/<int:topic_id>')
@login_required
@topics_blueprint.with_dictionnary
def viewTopic(topic_id):
	topic = MqttTopic.storage.get(id=topic_id)
	if topic is None:
		return abort(404)

	return AuthenticatedUserTemplate(
		Path(topics_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("view.html"),
		topic=topic,
	).handles_success_and_error().with_dictionnary().with_sidebar("topics").render()



@topics_blueprint.route('/topic/<int:topic_id>', methods=["PUT", "PATCH"])
@login_required
@body_content('json')
def editTopic(form, topic_id):
    topic = MqttTopic.storage.get(id=topic_id)
    if topic is None:
        return abort(404)

    topic.takeSnapshot().setAttributes(
        **{field: form.get(field, topic[field]) for field in MqttTopic.UPDATABLE_FIELDS}
    )

    if form.get('code') is not None:
    	code_filename = "_".join([topic['name'].lower().replace(" ","_"), topic['version'].lower().replace('.','_')])
    	TOPICS_DB.write(code_filename, form['code'], mode="")
    	code_filename_with_suffix = f"{code_filename}.{MqttTopic.FILE_EXTENSIONS[topic['language'].lower()].lower()}"
    	TOPICS_DB.write(code_filename_with_suffix, form['code'], mode="")

    MqttTopic.storage.updateOnSnapshot(topic)
    return {"status":"updated", "data":topic.to_dict()}


@topics_blueprint.route('/topic/<int:topic_id>', methods=["DELETE"])
@login_required
def deleteMqttTopic(topic_id):
    topic = MqttTopic.storage.get(id=topic_id)
    if topic is None:
        return abort(404)

    MqttTopic.storage.delete(topic)
    return {"status":"deleted", "data":topic.to_dict()}