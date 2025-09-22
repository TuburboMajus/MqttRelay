from flask import current_app, render_template, request, redirect, url_for, abort, session,g
from flask_login import LoginManager, login_required, current_user

from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.encoding import iri_to_uri

from temod_flask.utils.content_readers import body_content
from temod_flask.blueprint import MultiLanguageBlueprint

from front.renderers.base import BaseTemplate

from datetime import datetime, date
from pathlib import Path

import traceback


auth_blueprint = MultiLanguageBlueprint('auth',__name__, load_in_g=True, default_config={
	"templates_folder":"{language}/auth",
	"authenticator":LoginManager,
}, dictionnary_selector=lambda lg:lg['code'])


# ** EndSection ** Routes
@auth_blueprint.route('/login',methods=['GET'])
@auth_blueprint.with_language
def login():
	if not current_user.is_anonymous:
		auth_blueprint.get_configuration('authenticator').logout_user(current_user)
		
	return BaseTemplate(
		Path(auth_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("login.html"), 
		languages=current_app.config['LANGUAGES'].values(),
	).handles_error().with_language().render()


@auth_blueprint.route('/login',methods=['POST'])
@body_content("form")
@auth_blueprint.with_dictionnary
def dologin(form):
	
	try:
		form.update({"email":form['email'].strip()})
	except:
		return redirect(url_for("auth.login"))

	authenticator = auth_blueprint.get_configuration('authenticator')
	user = authenticator.search_user(form["email"])

	dictionnary = current_app.config['DICTIONNARY'][user['language']]
	if user is not None and user['user'].attributes['password'] == form.get('password'):
		if user['is_disabled']:
			error = dictionnary['login']["account_deactivated"]
		else:
			authenticator.login_user(user, remember=form.get("remember")=="on")
			next_ = request.args.get('next')
			if next_ is not None:
				if not url_has_allowed_host_and_scheme(next_, request.host):
					return abort(400)
				else:
					next_ = iri_to_uri(next_)
			session['lg'] = user['language']
			return redirect(next_ or "/")
	else:
		error = dictionnary['login']["wrong_identifiers"]

	return redirect(url_for("auth.login",error=error))





@auth_blueprint.route('/signup',methods=['GET'])
@auth_blueprint.with_language
def signup():
	if not current_user.is_anonymous:
		auth_blueprint.get_configuration('authenticator').logout_user(current_user)

	return BaseTemplate( 
		Path(auth_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("signup.html"), 
		languages=current_app.config['LANGUAGES'].values()
	).handles_error().with_language().render()
		

@auth_blueprint.route('/signup',methods=['POST'])
@body_content("form")
@auth_blueprint.with_dictionnary
def doSignup(form):

	try:

		form.update({"email":form['email'].strip(),"username":form['name'].strip()})
		user = User.storage.get(email=form['email'])

		if user is None:

			password = form.get('password')
			cpassword = form.get('cpassword')
			if password == cpassword:
				user = User(
					id=User.storage.generate_value('id'),
					privilege=Privilege.storage.get(label="admin")['id'],
					email=form['email'],
					language=g.language['code']
				)
				user['password'] = password
				User.storage.create(user)
				return redirect(url_for('auth.login'))

			error = g.dictionnary['signup']['unmatched_passwords']

		elif user is not None:
			error = g.dictionnary['signup']['email_already_used']

	except:
		traceback.print_exc()
		error = g.dictionnary['signup']['email_error']

	return redirect(url_for('auth.signup',error=error))
	

@auth_blueprint.route('/logout',methods=['GET',"POST"])
@login_required
def logout():
	auth_blueprint.get_configuration('authenticator').logout_user(current_user)
	return redirect(url_for('auth.login'))
# ** EndSection ** Routes