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


metrics_blueprint = MultiLanguageBlueprint('metrics',__name__, load_in_g=True, default_config={
	"templates_folder":"{language}/metrics",
	"metrics_per_page":100,
}, dictionnary_selector=lambda lg:lg['code'])


@metrics_blueprint.route('/metrics')
@login_required
@Paginator(metrics_blueprint, page_size_config="metrics_per_page").for_entity(Metric).with_default_filter(True).paginate
@metrics_blueprint.with_dictionnary
def listMetrics(pagination):
	return pagination.to_dict()['current']


@metrics_blueprint.route('/metric')
@login_required
@metrics_blueprint.with_dictionnary
def newMetric():
	return AuthenticatedUserTemplate(
		Path(metrics_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("new.html"),
	).handles_success_and_error().with_dictionnary().with_sidebar("metrics").render()


@metrics_blueprint.route('/metric',methods=["POST"])
@login_required
@body_content('json')
def createMetric(form):
	metric = Metric(id=-1,**form)
	Metric.storage.create(metric)
	return redirect(url_for("metrics.listMetrics"))


@metrics_blueprint.route('/metric/<int:metric_id>')
@login_required
@metrics_blueprint.with_dictionnary
def viewMetric(metric_id):
	metric = Metric.storage.get(id=metric_id)
	if metric is None:
		return abort(404)

	return AuthenticatedUserTemplate(
		Path(metrics_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("view.html"),
		metric=metric
	).handles_success_and_error().with_dictionnary().with_sidebar("metrics").render()



@metrics_blueprint.route('/metric/<int:metric_id>', methods=["PUT", "PATCH"])
@login_required
@body_content('json')
def editMetric(form, metric_id):
    metric = Metric.storage.get(id=metric_id)
    if metric is None:
        return abort(404)

    metric.takeSnapshot().setAttributes(
        **{field: form.get(field, metric[field]) for field in Metric.UPDATABLE_FIELDS}
    )
    Metric.storage.updateOnSnapshot(metric)
    return {"status":"updated", "data":metric.to_dict()}


@metrics_blueprint.route('/metric/<int:metric_id>', methods=["DELETE"])
@login_required
def deleteMetric(metric_id):
    metric = Metric.storage.get(id=metric_id)
    if metric is None:
        return abort(404)

    Metric.storage.delete(metric)
    return {"status":"deleted", "data":metric.to_dict()}