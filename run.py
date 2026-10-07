from flask import Flask, redirect, url_for, g, session, request
from flask_mqtt import Mqtt
from flask_login import current_user, login_required, LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from context import *
from core.models import User, Language
from core.repository import repos
from core.auth import get_user_by_id

import traceback
import mimetypes
import yaml
import toml
import json
import logging
import ssl
import os
import secrets


def generate_secret_key(length: int = 32) -> str:
    """Generate a random secret key for Flask."""
    return secrets.token_hex(length // 2 )


# ** Section ** MimetypesDefinition
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('text/css', '.min.css')
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('text/javascript', '.min.js')
# ** EndSection ** MimetypesDefinition


# ** Section ** LoadConfiguration
with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),"config.toml")) as config_file:
	config = toml.load(config_file)

with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),"dictionnary.yml")) as dictionnary_file:
    dictionnary = yaml.safe_load(dictionnary_file.read())
# ** EndSection ** LoadConfiguration


# ** Section ** ContextCreation
init_context(config)
# ** EndSection ** ContextCreation

# ** Section ** AppCreation
def update_configuration(original_config, new_config):
    new_keys = set(new_config).difference(set(original_config))
    common_keys = set(new_config).intersection(set(original_config))
    for k in common_keys:
        if type(original_config[k]) is dict and type(new_config[k]) is not dict:
            raise Exception("Unmatched config type")
        if type(original_config[k]) is dict:
            update_configuration(original_config[k],new_config[k])
        else:
            original_config[k] = new_config[k]
    for k in new_keys:
        original_config[k] = new_config[k]

def build_app(**app_configuration):

	update_configuration(config,app_configuration)

	app = Flask(
		__name__,
		template_folder=config['app']['templates_folder'],
		static_folder=config['app']['static_folder']
	)
	csrf = CSRFProtect(app)
	# In-memory storage is fine for this single-container deployment; move to a shared
	# Redis backend (storage_uri='redis://...') if the web service is ever scaled
	# horizontally, since in-memory limits are per-process and wouldn't be shared.
	limiter = Limiter(get_remote_address, app=app, storage_uri='memory://')

	secret_key = config['app'].get('secret_key','')
	app.secret_key = secret_key if len(secret_key) > 0 else generate_secret_key(32)

	# ** Section ** LoggingLevel
	_log_level = (config['app'].get('log_level') or ('DEBUG' if config['app'].get('debug') else 'INFO')).strip().upper()
	app.logger.setLevel(getattr(logging, _log_level, logging.INFO))
	# ** EndSection ** LoggingLevel

	app.config.update({k:v for k,v in config['app'].items() if not type(v) is dict})
	app.config.update({
		'SESSION_COOKIE_HTTPONLY': True,
		'SESSION_COOKIE_SAMESITE': 'Lax',
		'SESSION_COOKIE_SECURE': config['app'].get('ssl', False),
	})
	app.config.update({f"MQTT_{k.upper()}":v for k,v in config['mqtt'].items() if not type(v) is dict})
	# flask-mqtt defaults tls_version to the deprecated ssl.PROTOCOL_TLSv1, which modern
	# brokers reject (TLS handshake never completes -> on_connect/subscribe never fire).
	# Force the non-deprecated auto-negotiating TLS client context unless overridden.
	app.config.setdefault('MQTT_TLS_VERSION', ssl.PROTOCOL_TLS_CLIENT)
	# Load languages from database
	languages = repos['Language'].list()
	app.config['LANGUAGES'] = {lang.code: {'code': lang.code, 'name': lang.name} for lang in languages}
	if not app.config['LANGUAGES']:
		print("Warning: No languages configured in database")
	print(app.config['LANGUAGES'])
	app.config['DICTIONNARY'] = dictionnary

	# ** Section ** Blueprint
	import blueprints

	# ** Section ** Authentification
	login_manager = LoginManager()
	login_manager.init_app(app)
	login_manager.login_view = 'auth.login'

	@login_manager.user_loader
	def load_user(user_id):
		return get_user_by_id(user_id)
	# ** EndSection ** Authentification

	# ** Section ** LanguageContext
	@app.before_request
	def set_language():
		lang_code = session.get('lg') or request.args.get('lg')
		if not lang_code or lang_code not in app.config['LANGUAGES']:
			lang_code = config['app'].get('default_language', 'en')
		if lang_code not in app.config['LANGUAGES'] and app.config['LANGUAGES']:
			lang_code = next(iter(app.config['LANGUAGES']))
		g.language = app.config['LANGUAGES'].get(lang_code, {'code': 'en', 'name': 'English'})

	@app.context_processor
	def inject_globals():
		return {
			'language': g.get('language', {'code': 'en', 'name': 'English'}),
			'languages': app.config['LANGUAGES'].values(),
			'dictionnary': app.config.get('DICTIONNARY', {}),
		}
	# ** EndSection ** LanguageContext

	auth_blueprint_config = config['app'].get('blueprints',{}).get('auth',{})

	mqtt_blueprint_config = config['app'].get('blueprints',{}).get('mqtt',{})
	app.register_blueprint(blueprints.destinations.setup(config['app'].get('blueprints',{}).get('destinations',{})))
	app.register_blueprint(blueprints.dashboard.setup(config['app'].get('blueprints',{}).get('dashboard',{})))
	app.register_blueprint(blueprints.clients.setup(config['app'].get('blueprints',{}).get('clients',{})))
	app.register_blueprint(blueprints.devices.setup(config['app'].get('blueprints',{}).get('devices',{})))
	app.register_blueprint(blueprints.parsers.setup(config['app'].get('blueprints',{}).get('parsers',{})))
	app.register_blueprint(blueprints.general.setup(config['app'].get('blueprints',{}).get('general',{})))
	app.register_blueprint(blueprints.metrics.setup(config['app'].get('blueprints',{}).get('metrics',{})))
	app.register_blueprint(blueprints.topics.setup(config['app'].get('blueprints',{}).get('topics',{})))
	app.register_blueprint(blueprints.routes.setup(config['app'].get('blueprints',{}).get('routes',{})))
	app.register_blueprint(blueprints.users.setup(config['app'].get('blueprints',{}).get('users',{})))
	mqtt_bp = blueprints.mqtt.setup(mqtt_blueprint_config)
	blueprints.mqtt.setup_mqtt(Mqtt(app, connect_async=True))
	app.register_blueprint(mqtt_bp)
	app.register_blueprint(blueprints.auth.setup(auth_blueprint_config))
	# ** EndSection ** Blueprint**

	# ** Section ** RateLimits
	# Apply limits directly to the already-registered view functions (keyed by their
	# blueprint-qualified endpoint name) rather than importing the blueprints' view
	# modules here, to avoid a circular import between run.py and blueprints/*.py.
	app.view_functions['auth.dologin'] = limiter.limit("10 per minute;100 per hour")(app.view_functions['auth.dologin'])
	app.view_functions['auth.doSignup'] = limiter.limit("5 per minute")(app.view_functions['auth.doSignup'])
	app.view_functions['users.changePassword'] = limiter.limit("10 per minute")(app.view_functions['users.changePassword'])
	# ** EndSection ** RateLimits

	# ** Section ** AppMainRoutes
	@app.route('/', methods=['GET'])
	@login_required
	def home():
		return redirect(url_for('dashboard.dashboard'))
	# ** EndSection ** AppMainRoutes

	return app
# ** EndSection ** AppCreation


if __name__ == '__main__':

	app = build_app(**config)

	server_configs = {
		"host":config['app']['host'], "port":config['app']['port'],
		"threaded":config['app']['threaded'],"debug":config['app']['debug']
	}
	if config['app'].get('ssl',False):
		server_configs['ssl_context'] = (config['app']['ssl_cert'],config['app']['ssl_key'])

	app.run(**server_configs)
