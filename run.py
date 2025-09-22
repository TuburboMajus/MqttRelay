from flask import Flask, redirect, url_for
from flask_mqtt import Mqtt
from flask_login import current_user, login_required

from temod_flask.security.authentification import Authenticator, TemodUserHandler

from temod.ext.holders import init_holders

from context import *

import traceback
import mimetypes
import yaml
import toml
import json
import os


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
init_holders(
	entities_dir=os.path.join(config['temod']['core_directory'],r"entity"),
	joins_dir=os.path.join(config['temod']['core_directory'],r"join"),
	databases=config['temod']['bound_database'],
	db_credentials=config['storage']['credentials']
)
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

	secret_key = config['app'].get('secret_key','')
	app.secret_key = secret_key if len(secret_key) > 0 else generate_secret_key(32)
	app.config.update({k:v for k,v in config['app'].items() if not type(v) is dict})
	app.config.update({f"MQTT_{k.upper()}":v for k,v in config['mqtt'].items() if not type(v) is dict})
	app.config['LANGUAGES'] = {language["code"]:language for language in Language.storage.list()}
	app.config['DICTIONNARY'] = dictionnary

	# ** Section ** Blueprint
	import blueprints

	# ** Section ** Authentification
	AUTHENTICATOR = Authenticator(TemodUserHandler(
		joins.UserAccount, "mysql", logins=['email'], **config['storage']['credentials']
	),login_view="auth.login")
	AUTHENTICATOR.init_app(app)
	# ** EndSection ** Authentification

	auth_blueprint_config = config['app'].get('blueprints',{}).get('auth',{})
	auth_blueprint_config['authenticator'] = AUTHENTICATOR

	mqtt_blueprint_config = config['app'].get('blueprints',{}).get('mqtt',{})
	app.register_blueprint(blueprints.destinations_blueprint.setup(config['app'].get('blueprints',{}).get('destinations',{})))
	app.register_blueprint(blueprints.dashboard_blueprint.setup(config['app'].get('blueprints',{}).get('dashboard',{})))
	app.register_blueprint(blueprints.clients_blueprint.setup(config['app'].get('blueprints',{}).get('clients',{})))
	app.register_blueprint(blueprints.devices_blueprint.setup(config['app'].get('blueprints',{}).get('devices',{})))
	app.register_blueprint(blueprints.parsers_blueprint.setup(config['app'].get('blueprints',{}).get('parsers',{})))
	app.register_blueprint(blueprints.general_blueprint.setup(config['app'].get('blueprints',{}).get('general',{})))
	app.register_blueprint(blueprints.metrics_blueprint.setup(config['app'].get('blueprints',{}).get('metrics',{})))
	app.register_blueprint(blueprints.topics_blueprint.setup(config['app'].get('blueprints',{}).get('topics',{})))
	app.register_blueprint(blueprints.routes_blueprint.setup(config['app'].get('blueprints',{}).get('routes',{})))
	app.register_blueprint(blueprints.users_blueprint.setup(config['app'].get('blueprints',{}).get('users',{})))
	app.register_blueprint(blueprints.mqtt_blueprint.setup(mqtt_blueprint_config).setup_mqtt(Mqtt(app)))
	app.register_blueprint(blueprints.auth_blueprint.setup(auth_blueprint_config))
	# ** EndSection ** Blueprint**

	# ** Section ** AppMainRoutes
	@app.route('/', methods=['GET'])
	@login_required
	def home():
		return redirect(url_for('clients.listClients'))
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
