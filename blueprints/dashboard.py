from flask import current_app, render_template, request, redirect, url_for, abort, session,g,jsonify
from flask_login import LoginManager, login_required, current_user

from temod_flask.utils.content_readers import body_content
from temod_flask.blueprint import MultiLanguageBlueprint
from temod_flask.blueprint.utils import Paginator

from front.renderers.users import AuthenticatedUserTemplate

from .dashboards import *

from datetime import datetime, date
from pathlib import Path

import traceback
import json


dashboard_blueprint = MultiLanguageBlueprint('dashboard',__name__, load_in_g=True, default_config={
	"templates_folder":"{language}/dashboard",
	"general_per_page":100,
}, dictionnary_selector=lambda lg:lg['code'])



@dashboard_blueprint.route('/dashboard', methods=['GET'])
@login_required
@dashboard_blueprint.with_dictionnary
def dashboard():
	return AuthenticatedUserTemplate(
	Path(dashboard_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("dashboard.html")
).handles_success_and_error().with_dictionnary().with_sidebar("dashboard").render()



@dashboard_blueprint.route('/dashboard/api/critical/ingest_rate', methods=['GET'])
@login_required
@dashboard_blueprint.with_dictionnary
def ingest_rate_data():
	"""
	Query params:
	  - range: '5m'|'1h'|'2h'|'24h'|'7d'|'30d' (default '2h')
	  - client: numeric client_id OR a slug/name (we try int first)
	Response: { "value": <float rounded to 1 decimal> }
	"""

	rng = request.args.get("range", "2h")
	client_raw = request.args.get("client")

	client_id: Optional[int] = None
	client_slug: Optional[str] = None
	if client_raw:
		try:
			client_id = int(client_raw)
		except ValueError:
			client_slug = client_raw

	try:
		rate = ingest_rate.compute(range_str=rng, client_id=client_id, client_slug_or_name=client_slug)
		return {"value": round(rate, 1)}
	except Exception as e:
		traceback.print_exc()
		return jsonify({"value": None, "error": str(e)}), 500



@dashboard_blueprint.route('/dashboard/api/critical/parse_success', methods=['GET'])
@login_required
@dashboard_blueprint.with_dictionnary
def success_parse_data():
	rng = request.args.get("range", "2h")
	client_raw = request.args.get("client")

	client_id: Optional[int] = None
	client_slug: Optional[str] = None
	if client_raw:
		try:
			client_id = int(client_raw)
		except ValueError:
			client_slug = client_raw

	try:
		pct = parse_success.compute(range_str=rng, client_id=client_id, client_slug_or_name=client_slug)
		return jsonify({"value": round(pct, 1)})
	except Exception as e:
		traceback.print_exc()
		return jsonify({"value": 0.0, "error": str(e)}), 500



@dashboard_blueprint.route('/dashboard/api/critical/dispatch_success', methods=['GET'])
@login_required
@dashboard_blueprint.with_dictionnary
def dispatch_success_data():
	rng = request.args.get("range", "2h")
	client_raw = request.args.get("client")

	client_id: Optional[int] = None
	client_slug: Optional[str] = None
	if client_raw:
		try:
			client_id = int(client_raw)
		except ValueError:
			client_slug = client_raw

	try:
		pct = dispatch_success.compute(range_str=rng, client_id=client_id, client_slug_or_name=client_slug)
		return jsonify({"value": round(pct, 1)})
	except Exception as e:
		traceback.print_exc()
		return jsonify({"value": 0.0, "error": str(e)}), 500



@dashboard_blueprint.route('/dashboard/api/critical/processing_backlog', methods=['GET'])
@login_required
@dashboard_blueprint.with_dictionnary
def processing_backlog_data():
	client_raw = request.args.get("client")

	client_id: Optional[int] = None
	client_slug: Optional[str] = None
	max_age = request.args.get("max_age")
	if client_raw:
		try:
			client_id = int(client_raw)
		except ValueError:
			client_slug = client_raw

	try:
		pct = processing_backlog.compute(max_age=max_age, client_id=client_id, client_slug_or_name=client_slug)
		return jsonify({"value": round(pct, 1)})
	except Exception as e:
		traceback.print_exc()
		return jsonify({"value": 0.0, "error": str(e)}), 500



@dashboard_blueprint.route('/dashboard/api/critical/throughput_series', methods=['GET'])
@login_required
@dashboard_blueprint.with_dictionnary
def ingest_throughtput_data():
	rng = request.args.get("range", "2h")
	client_raw = request.args.get("client")
	bucket = request.args.get("bucket", "auto")

	client_id: Optional[int] = None
	client_slug: Optional[str] = None
	if client_raw:
		try:
			client_id = int(client_raw)
		except ValueError:
			client_slug = client_raw

	try:
		payload = throughput_series.compute(
			range_str=rng,
			client_id=client_id,
			client_slug_or_name=client_slug,
			bucket=bucket,
		)
		return jsonify(payload)
	except Exception as e:
		traceback.print_exc()
		return jsonify({"labels": [], "datasets": [], "error": str(e)}), 500



@dashboard_blueprint.route('/dashboard/api/critical/dispatch_series', methods=['GET'])
@login_required
@dashboard_blueprint.with_dictionnary
def dispatch_series_data():
	rng = request.args.get("range", "24h")
	client_raw = request.args.get("client")
	bucket = request.args.get("bucket", "auto")

	client_id: Optional[int] = None
	client_slug: Optional[str] = None
	if client_raw:
		try:
			client_id = int(client_raw)
		except ValueError:
			client_slug = client_raw

	try:
		payload = dispatch_series.compute(
			range_str=rng, client_id=client_id, client_slug=client_slug, bucket=bucket
		)
		return jsonify(payload)
	except Exception as e:
		traceback.print_exc()
		return jsonify({"labels": [], "datasets": [], "error": str(e)}), 500