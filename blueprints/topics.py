from flask import current_app, render_template, request, redirect, url_for, abort, session, g, jsonify, Blueprint
from flask_login import login_required, current_user

from core.repository import repos
from core.pagination import paginate
from core.models import MqttTopic, Device, MqttMessage
from core.validation import parse_int_bounded

from datetime import datetime, date
import logging


bp = Blueprint('topics', __name__)

def setup(config=None):
    """Setup topics blueprint with configuration."""
    return bp


@bp.route('/topics')
@login_required
def listTopics():
    current_app.logger.debug("Route [topics.listTopics] called (json=%s, page=%s)", request.args.get('json'), request.args.get('page'))
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    pagination = paginate(repos['MqttTopic'], page=page, per_page=per_page)
    
    if request.args.get('json', 'false').lower() in ["1", "true"]:
        return jsonify(pagination.to_dict())
    
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/topics/list.html",
        pagination=pagination
    )


@bp.route('/unlinked_topics')
@login_required
def listUnlnkedTopics():
    current_app.logger.debug("Route [topics.listUnlnkedTopics] called (json=%s, page=%s)", request.args.get('json'), request.args.get('page'))
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    # Fetch topics that don't have associated devices
    # TODO: Implement proper filtering logic if needed
    pagination = paginate(repos['MqttTopic'], page=page, per_page=per_page)
    
    if request.args.get('json', 'false').lower() in ["1", "true"]:
        return jsonify(pagination.to_dict())
    
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/topics/list.html",
        pagination=pagination
    )


@bp.route('/topic')
@login_required
def newTopic():
    current_app.logger.debug("Route [topics.newTopic] serving new topic form")
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/topics/new.html"
    )


@bp.route('/topic', methods=["POST"])
@login_required
def createTopic():
    current_app.logger.debug("Route [topics.createTopic] creating topic")
    data = request.form.to_dict() if request.form else request.get_json()

    try:
        qos_default = parse_int_bounded(data.get('qos_default'), 'qos_default', 0, 2, default=0)
    except ValueError as e:
        current_app.logger.warning("Route [topics.createTopic] validation error: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 400

    topic = MqttTopic(
        topic=data.get('topic'),
        description=data.get('description'),
        qos_default=qos_default,
        active=data.get('active', 'on').lower() in ['on', '1', 'true'] if isinstance(data.get('active', 'on'), str) else bool(data.get('active')),
        client_id=data.get('client_id'),
        device_id=data.get('device_id'),
        created_at=datetime.utcnow()
    )
    repos['MqttTopic'].create(topic)
    current_app.logger.info("Route [topics.createTopic] topic created (id=%s)", topic.id)
    return redirect(url_for("topics.listTopics"))


@bp.route('/topic/<int:topic_id>')
@login_required
def viewTopic(topic_id):
    current_app.logger.debug("Route [topics.viewTopic] called (topic_id=%s)", topic_id)
    topic = repos['MqttTopic'].get(id=topic_id)
    if topic is None:
        current_app.logger.warning("Route [topics.viewTopic] topic not found (id=%s)", topic_id)
        return abort(404)

    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/topics/view.html",
        topic=topic
    )



@bp.route('/topic/<int:topic_id>', methods=["PUT", "PATCH"])
@login_required
def editTopic(topic_id):
    current_app.logger.debug("Route [topics.editTopic] called (topic_id=%s)", topic_id)
    topic = repos['MqttTopic'].get(id=topic_id)
    if topic is None:
        current_app.logger.warning("Route [topics.editTopic] topic not found (id=%s)", topic_id)
        return abort(404)

    data = request.get_json() or request.form.to_dict()
    updatable = {'topic', 'description', 'qos_default', 'active', 'client_id', 'device_id'}
    update_dict = {k: v for k, v in data.items() if k in updatable}
    
    # Handle boolean conversion for active field
    if 'active' in update_dict:
        update_dict['active'] = update_dict['active'].lower() in ['true', '1', 'on'] if isinstance(update_dict['active'], str) else bool(update_dict['active'])
    
    # Handle integer conversion for qos_default
    if 'qos_default' in update_dict:
        try:
            update_dict['qos_default'] = parse_int_bounded(update_dict['qos_default'], 'qos_default', 0, 2, default=0)
        except ValueError as e:
            current_app.logger.warning("Route [topics.editTopic] validation error: %s", e)
            return jsonify({"status": "error", "error": str(e)}), 400
    
    repos['MqttTopic'].update(topic, **update_dict)
    current_app.logger.info("Route [topics.editTopic] topic updated (id=%s)", topic_id)
    return jsonify(status="updated", data=topic.to_dict())


@bp.route('/topic/<int:topic_id>', methods=["DELETE"])
@login_required
def deleteMqttTopic(topic_id):
    current_app.logger.debug("Route [topics.deleteMqttTopic] called (topic_id=%s)", topic_id)
    topic = repos['MqttTopic'].get(id=topic_id)
    if topic is None:
        current_app.logger.warning("Route [topics.deleteMqttTopic] topic not found (id=%s)", topic_id)
        return abort(404)

    topic_dict = topic.to_dict()
    repos['MqttTopic'].delete(topic)
    current_app.logger.info("Route [topics.deleteMqttTopic] topic deleted (id=%s)", topic_id)
    return jsonify(status="deleted", data=topic_dict)