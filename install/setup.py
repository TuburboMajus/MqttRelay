from temod.storage.mysql import MysqlEntityStorage
from subprocess import Popen, PIPE, STDOUT
from pathlib import Path
from uuid import uuid4 

import sys
import os

if not os.getcwd() in sys.path:
	sys.path.append(os.getcwd())

from install import common_funcs
from core.entity import *

import mysql.connector
import traceback
import argparse
import toml
import re


APP_VERSION = "1.0.0"


def search_existing_database(credentials):
	try:
		connexion = mysql.connector.connect(**credentials)
	except:
		LOGGER.error("Can't connect to the specified database using these credentials. Verify the credentials and the existence of the database.")
		LOGGER.error(traceback.format_exc())
		sys.exit(1)

	cursor = connexion.cursor()
	cursor.execute('show tables;')

	try:
		return len(cursor.fetchall()) > 0
	except:
		raise
	finally:
		cursor.close()
		connexion.close()


def confirm_database_overwrite():
	print(); common_funcs.print_decorated_title("! DANGER"); print()
	LOGGER.info("The specified database already exists and is not empty. This installation script will erase all the database content and overwrite it with a clean one.")
	rpsn = input("Continue the installation (y/*) ?").lower()
	return rpsn == "y"


def install_preset_objects(credentials):	
	mqtt_relay = MqttRelay(version=APP_VERSION)
	MysqlEntityStorage(MqttRelay,**credentials).create(mqtt_relay)
	return True


def setup(app_paths, args):

	credentials = common_funcs.get_mysql_credentials()

	already_created = search_existing_database(credentials)
	if already_created:
		if not confirm_database_overwrite():
			LOGGER.warning("If you which to just update the app, run the script install/update.py")
			return False

	with open(app_paths['mysql_schema_file']) as file:
		if not common_funcs.execute_mysql_script(credentials, file.read().replace("$database",credentials['database'])):
			return False

	template_config = common_funcs.load_toml_config(app_paths['template_config_file'])
	template_config['storage']['credentials'].update(credentials)
	common_funcs.save_toml_config(template_config, app_paths['config_file'])

	return install_preset_objects(credentials)


if __name__ == "__main__":

	print("\n"); width = common_funcs.print_pattern("MqttRelay Server"); print(); print("#"*width); print()

	parser = argparse.ArgumentParser(prog="Installs a MqttRelay server")
	parser.add_argument(
		'-l', '--logging-dir', help='Directory where log files will be stored', 
		default=os.path.join("/","var","log","mqtt_relay")
	)
	parser.add_argument('-q', '--quiet', action="store_true", help='No logging', default=False)
	args = parser.parse_args()

	setattr(__builtins__,'LOGGER', common_funcs.get_logger(args.logging_dir, quiet=args.quiet))
	app_paths = common_funcs.get_app_paths(Path(os.path.realpath(__file__)).parent)

	if not os.path.isfile(app_paths['mysql_schema_file']):
		LOGGER.error("DB schema file not found at",app_paths['mysql_schema_file'])
		sys.exit(1)

	if not os.path.isfile(app_paths['template_config_file']):
		LOGGER.error("Config template file not found at",app_paths['template_config_file'])
		sys.exit(1)

	if setup(app_paths, args):
		LOGGER.info("MqttRelay setup completed successfully")
	else:
		LOGGER.error("Error while installing Over")
		exit(1)