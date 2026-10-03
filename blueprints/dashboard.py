from flask import current_app, render_template, request, redirect, url_for, abort, session, g, jsonify, Blueprint
from flask_login import login_required, current_user

from .dashboards import *

from datetime import datetime, date
from typing import Optional
import traceback


bp = Blueprint('dashboard', __name__)

def setup(config=None):
    """Setup dashboard blueprint with configuration."""
    return bp



@bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    current_app.logger.debug("Route [dashboard.dashboard] rendering dashboard page")
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/dashboard/dashboard.html"
    )



@bp.route('/dashboard/api/critical/ingest_rate', methods=['GET'])
@login_required
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

    current_app.logger.debug("Route [dashboard.ingest_rate_data] called (range=%s, client=%s)", rng, client_raw)

    try:
        rate = ingest_rate.compute(range_str=rng, client_id=client_id, client_slug_or_name=client_slug)
        return jsonify({"value": round(rate, 1)})
    except Exception as e:
        traceback.print_exc()
        current_app.logger.exception("Route [dashboard.ingest_rate_data] compute failed: %s", e)
        return jsonify({"value": None, "error": str(e)}), 500



@bp.route('/dashboard/api/critical/parse_success', methods=['GET'])
@login_required
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

    current_app.logger.debug("Route [dashboard.success_parse_data] called (range=%s, client=%s)", rng, client_raw)

    try:
        pct = parse_success.compute(range_str=rng, client_id=client_id, client_slug_or_name=client_slug)
        return jsonify({"value": round(pct, 1)})
    except Exception as e:
        traceback.print_exc()
        current_app.logger.exception("Route [dashboard.success_parse_data] compute failed: %s", e)
        return jsonify({"value": 0.0, "error": str(e)}), 500



@bp.route('/dashboard/api/critical/dispatch_success', methods=['GET'])
@login_required
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

    current_app.logger.debug("Route [dashboard.dispatch_success_data] called (range=%s, client=%s)", rng, client_raw)

    try:
        pct = dispatch_success.compute(range_str=rng, client_id=client_id, client_slug_or_name=client_slug)
        return jsonify({"value": round(pct, 1)})
    except Exception as e:
        traceback.print_exc()
        current_app.logger.exception("Route [dashboard.dispatch_success_data] compute failed: %s", e)
        return jsonify({"value": 0.0, "error": str(e)}), 500



@bp.route('/dashboard/api/critical/processing_backlog', methods=['GET'])
@login_required
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

    current_app.logger.debug("Route [dashboard.processing_backlog_data] called (client=%s, max_age=%s)", client_raw, max_age)

    try:
        pct = processing_backlog.compute(max_age=max_age, client_id=client_id, client_slug_or_name=client_slug)
        return jsonify({"value": round(pct, 1)})
    except Exception as e:
        traceback.print_exc()
        current_app.logger.exception("Route [dashboard.processing_backlog_data] compute failed: %s", e)
        return jsonify({"value": 0.0, "error": str(e)}), 500



@bp.route('/dashboard/api/critical/throughput_series', methods=['GET'])
@login_required
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

    current_app.logger.debug("Route [dashboard.ingest_throughtput_data] called (range=%s, client=%s, bucket=%s)", rng, client_raw, bucket)

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
        current_app.logger.exception("Route [dashboard.ingest_throughtput_data] compute failed: %s", e)
        return jsonify({"labels": [], "datasets": [], "error": str(e)}), 500



@bp.route('/dashboard/api/critical/dispatch_series', methods=['GET'])
@login_required
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

    current_app.logger.debug("Route [dashboard.dispatch_series_data] called (range=%s, client=%s, bucket=%s)", rng, client_raw, bucket)

    try:
        payload = dispatch_series.compute(
            range_str=rng, client_id=client_id, client_slug=client_slug, bucket=bucket
        )
        return jsonify(payload)
    except Exception as e:
        traceback.print_exc()
        current_app.logger.exception("Route [dashboard.dispatch_series_data] compute failed: %s", e)
        return jsonify({"labels": [], "datasets": [], "error": str(e)}), 500