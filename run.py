from flask import Flask
from flask_mqtt import Mqtt

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

	# ** Section ** Blueprint
	import blueprints

	mqtt_blueprint_config = config['app'].get('blueprints',{}).get('mqtt',{})
	app.register_blueprint(blueprints.mqtt_blueprint.setup(mqtt_blueprint_config).setup_mqtt(Mqtt(app)))
	# ** EndSection ** Blueprint**

	# ** Section ** AppMainRoutes
	@app.route('/', methods=['GET'])
	def home():
		if current_user.is_anonymous:
			if request.args.get("access") is not None:
				return redirect(url_for("auth.login",access=request.args.get("access")))
		return redirect(url_for('report.listReports'))
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
