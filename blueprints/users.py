from flask import current_app, render_template, request, redirect, url_for, abort, session, g, jsonify, Blueprint
from flask_login import login_required, current_user

from core.repository import repos
from core.pagination import paginate
from core.auth import hash_password, verify_password
from core.models import User, Privilege

from datetime import datetime, date
import logging


bp = Blueprint('users', __name__)

def setup(config=None):
    """Setup users blueprint with configuration."""
    return bp


@bp.route('/users')
@login_required
def listUsers():
    current_app.logger.debug("Route [users.listUsers] called (json=%s, page=%s)", request.args.get('json'), request.args.get('page'))
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    pagination = paginate(repos['User'], page=page, per_page=per_page)
    
    if request.args.get('json', 'false').lower() in ["1", "true"]:
        return jsonify(pagination.to_dict())
    
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/users/list.html",
        pagination=pagination
    )


@bp.route('/user')
@login_required
def newUser():
    current_app.logger.debug("Route [users.newUser] serving new user form")
    privileges = repos['Privilege'].list()
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/users/new.html",
        privileges=[p.to_dict() for p in privileges]
    )


@bp.route('/user', methods=["POST"])
@login_required
def createUser():
    current_app.logger.debug("Route [users.createUser] creating user")
    data = request.form.to_dict() if request.form else request.get_json()

    # Hash the password
    password_hash = hash_password(data.get('password', ''))

    # Privilege ids are strings (e.g. "admin-privilege"); resolve and validate.
    privilege = None
    if data.get('privilege_id'):
        privilege = repos['Privilege'].get(id=data['privilege_id'])
    if privilege is None:
        current_app.logger.warning("Route [users.createUser] unknown privilege (id=%s)", data.get('privilege_id'))
        return jsonify(status="error", error="unknown_privilege"), 400

    user = User(
        email=data.get('email'),
        privilege_id=privilege.id,
        password=password_hash,
        is_authenticated=True,
        is_active=data.get('is_active', 'true').lower() in ['true', '1', 'on'] if isinstance(data.get('is_active', 'true'), str) else bool(data.get('is_active')),
        is_disabled=data.get('is_disabled', 'false').lower() in ['true', '1', 'on'] if isinstance(data.get('is_disabled', 'false'), str) else bool(data.get('is_disabled')),
        language=data.get('language', 'en'),
        track=data.get('track', 'false').lower() in ['true', '1', 'on'] if isinstance(data.get('track', 'false'), str) else bool(data.get('track'))
    )
    repos['User'].create(user)
    current_app.logger.info("Route [users.createUser] user created (id=%s, email=%s)", user.id, user.email)
    return redirect(url_for("users.listUsers"))


@bp.route('/user/<string:user_id>')
@login_required
def viewUser(user_id):
    current_app.logger.debug("Route [users.viewUser] called (user_id=%s)", user_id)
    user = repos['User'].get(id=user_id)
    if user is None:
        current_app.logger.warning("Route [users.viewUser] user not found (id=%s)", user_id)
        return abort(404)

    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/users/view.html",
        user=user
    )


@bp.route('/user/<string:user_id>', methods=["PUT", "PATCH"])
@login_required
def editUser(user_id):
    current_app.logger.debug("Route [users.editUser] called (user_id=%s)", user_id)
    user = repos['User'].get(id=user_id)
    if user is None:
        current_app.logger.warning("Route [users.editUser] user not found (id=%s)", user_id)
        return abort(404)

    data = request.get_json() or request.form.to_dict()
    updatable = {'privilege_id', 'is_active', 'is_disabled', 'language', 'track'}
    update_dict = {k: v for k, v in data.items() if k in updatable}
    
    # Handle boolean conversions
    for bool_field in ['is_active', 'is_disabled', 'track']:
        if bool_field in update_dict:
            update_dict[bool_field] = update_dict[bool_field].lower() in ['true', '1', 'on'] if isinstance(update_dict[bool_field], str) else bool(update_dict[bool_field])
    
    repos['User'].update(user, **update_dict)
    current_app.logger.info("Route [users.editUser] user updated (id=%s)", user_id)
    return jsonify(status="updated", data=user.to_dict())


@bp.route('/user/<string:user_id>/password', methods=["PUT", "PATCH"])
@login_required
def changePassword(user_id):
    current_app.logger.debug("Route [users.changePassword] called (user_id=%s)", user_id)
    data = request.get_json() or request.form.to_dict()
    
    user = repos['User'].get(id=user_id)
    if user is None:
        current_app.logger.warning("Route [users.changePassword] user not found (id=%s)", user_id)
        return abort(404)

    # Check if user is changing their own password
    if user.id != current_user.get_id():
        current_app.logger.warning("Route [users.changePassword] user %s attempted to change password of another user %s", current_user.get_id(), user_id)
        return abort(403)

    # Verify current password
    if not verify_password(data.get('password', ''), user.password):
        current_app.logger.warning("Route [users.changePassword] wrong current password for user (id=%s)", user_id)
        return jsonify(status="error", data="Wrong current password")

    # Check password match
    if data.get('npassword') != data.get('cpassword'):
        current_app.logger.warning("Route [users.changePassword] new passwords do not match for user (id=%s)", user_id)
        return jsonify(status="error", data="New passwords do not match")

    # Check password length
    if len(data.get('npassword', '')) < 8:
        current_app.logger.warning("Route [users.changePassword] new password too short for user (id=%s)", user_id)
        return jsonify(status="error", data="Password must be at least 8 characters")

    # Update password
    new_password_hash = hash_password(data.get('npassword', ''))
    repos['User'].update(user, password=new_password_hash)
    
    current_app.logger.info("Route [users.changePassword] password changed for user (id=%s)", user_id)
    return jsonify(status="updated", data=user.to_dict())


@bp.route('/user/<string:user_id>', methods=["DELETE"])
@login_required
def deleteUser(user_id):
    current_app.logger.debug("Route [users.deleteUser] called (user_id=%s)", user_id)
    user = repos['User'].get(id=user_id)
    if user is None:
        current_app.logger.warning("Route [users.deleteUser] user not found (id=%s)", user_id)
        return abort(404)

    user_dict = user.to_dict()
    repos['User'].delete(user)
    current_app.logger.info("Route [users.deleteUser] user deleted (id=%s)", user_id)
    return jsonify(status="deleted", data=user_dict)