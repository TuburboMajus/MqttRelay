from flask import current_app, render_template, request, redirect, url_for, abort, session, g, Blueprint
from flask_login import login_required, current_user, login_user, logout_user

from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.encoding import iri_to_uri

from front.renderers.base import BaseTemplate
from core.repository import repos
from core.auth import authenticate_user, hash_password, validate_password, SQLAlchemyUserProxy
from core.models import User, Privilege

from datetime import datetime, date
from pathlib import Path

import traceback


auth_blueprint = Blueprint('auth', __name__)


def setup(config=None):
	"""Setup blueprint with configuration."""
	return auth_blueprint


# ** Section ** Routes
@auth_blueprint.route('/login', methods=['GET'])
def login():
	current_app.logger.debug("Route [auth.login] serving login page")
	if current_user and not current_user.is_anonymous:
		logout_user()
	
	# Get language from session or query param
	language_code = session.get('lg', g.get('language', {}).get('code', 'en'))

	# Bootstrap-only signup: hide the sign-up link once an account already exists
	user_exists = repos['User'].count() > 0

	return render_template(
		f'{language_code}/auth/login.html',
		languages=current_app.config['LANGUAGES'].values(),
		user_exists=user_exists,
		error=request.args.get('error'),
	)


@auth_blueprint.route('/login', methods=['POST'])
def dologin():
	current_app.logger.debug("Route [auth.dologin] login attempt for email=%s", request.form.get('email'))

	try:
		email = request.form.get('email', '').strip()
		password = request.form.get('password', '')
	except:
		current_app.logger.warning("Route [auth.dologin] malformed login form")
		return redirect(url_for("auth.login"))

	# Authenticate user
	user = authenticate_user(email, password)

	if user is not None:
		if not user.is_active:
			current_app.logger.warning("Route [auth.dologin] login rejected: account deactivated (email=%s)", email)
			error = "account_deactivated"
		else:
			current_app.logger.info("Route [auth.dologin] user authenticated (email=%s)", email)
			login_user(user, remember=request.form.get("remember") == "on")
			next_ = request.args.get('next')
			if next_ is not None:
				if not url_has_allowed_host_and_scheme(next_, request.host):
					current_app.logger.warning("Route [auth.dologin] open redirect blocked (next=%s)", next_)
					return abort(400)
				else:
					next_ = iri_to_uri(next_)
			session['lg'] = user._user.language
			return redirect(next_ or "/")
	else:
		current_app.logger.warning("Route [auth.dologin] login failed: wrong credentials (email=%s)", email)
		error = "wrong_identifiers"

	return redirect(url_for("auth.login", error=error))


@auth_blueprint.route('/signup', methods=['GET'])
def signup():
	current_app.logger.debug("Route [auth.signup] serving signup page")
	if current_user and not current_user.is_anonymous:
		logout_user()

	language_code = session.get('lg', g.get('language', {}).get('code', 'en'))

	# Bootstrap-only signup: once an account exists, show a message to contact
	# the administrator instead of the signup form.
	signup_disabled = repos['User'].count() > 0

	return render_template(
		f'{language_code}/auth/signup.html',
		languages=current_app.config['LANGUAGES'].values(),
		signup_disabled=signup_disabled,
		error=request.args.get('error'),
	)


@auth_blueprint.route('/signup', methods=['POST'])
def doSignup():
	current_app.logger.debug("Route [auth.doSignup] signup attempt for email=%s", request.form.get('email'))

	# Bootstrap-only signup: refuse to create any account once one already exists
	if repos['User'].count() > 0:
		current_app.logger.warning("Route [auth.doSignup] signup rejected: an account already exists (email=%s)", request.form.get('email'))
		return redirect(url_for('auth.signup', error="signup_disabled"))

	try:
		email = request.form.get('email', '').strip()
		name = request.form.get('name', '').strip()
		password = request.form.get('password', '')
		cpassword = request.form.get('cpassword', '')

		# Check if user already exists
		existing_user = repos['User'].get(email=email)

		if existing_user is None:
			if password == cpassword:
				password_error = validate_password(password)
				if password_error:
					current_app.logger.warning("Route [auth.doSignup] password too short (email=%s)", email)
					return redirect(url_for('auth.signup', error=password_error))

				# Create new user
				admin_privilege = repos['Privilege'].get(label="admin")
				new_user = User(
					id=None,  # Auto-generated
					privilege_id=admin_privilege.id if admin_privilege else None,
					email=email,
					password=hash_password(password),
					is_authenticated=False,
					is_active=True,
					is_disabled=False,
					language=session.get('lg', 'en'),
					track=False
				)
				repos['User'].create(new_user)
				current_app.logger.info("Route [auth.doSignup] user account created (email=%s)", email)
				return redirect(url_for('auth.login'))

			error = "unmatched_passwords"

		else:
			current_app.logger.warning("Route [auth.doSignup] email already in use (email=%s)", email)
			error = "email_already_used"

	except Exception as e:
		traceback.print_exc()
		current_app.logger.exception("Route [auth.doSignup] unexpected error during signup")
		error = "email_error"

	return redirect(url_for('auth.signup', error=error))


@auth_blueprint.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
	current_app.logger.info("Route [auth.logout] logging out user (id=%s)", current_user.id if current_user else None)
	logout_user()
	return redirect(url_for('auth.login'))
# ** EndSection ** Routes