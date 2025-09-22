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


APP_VERSION = "1.0.1"


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


def install_mqtttransfer_service(root_path, virtual_env, logging_dir, services_dir):
	# Install Overlord service
	with open(os.path.join(root_path,"services","mqtt_transfer","mqtt_transfer.service")) as file:
		service = file.read()
	service = service.replace("$script_path", os.path.join(root_path,"services","mqtt_transfer","mqtt_transfer.sh"))
	if virtual_env is not None:
		service = service.replace("$venv_path", f'-v "{os.path.join(virtual_env,"bin","activate")}"')
	else:
		service = service.replace("$venv_path", "")
	if logging_dir is not None:
		service = service.replace("$logging_dir", f'-l "{logging_dir}"')
	else:
		service = service.replace("$logging_dir", "")
	try:
		with open(os.path.join(services_dir,"mqtt_transfer.service"),"w") as file:
			file.write(service)
		with open(os.path.join(services_dir,"mqtt_transfer.timer"),"w") as file:
			with open(os.path.join(root_path,"services","mqtt_transfer","mqtt_transfer.timer"),"r") as ofile:
				file.write(ofile.read())
	except:
		LOGGER.error(f"Unable to save mqtt_transfer.service file in directory {services_dir}. You can either install the files in another directory with 'install.py -s [DIRECTORY]' or give enough rights to the install script.")
		LOGGER.error("Trace of the exception: ")
		LOGGER.error(traceback.format_exc())
		return False
	return True


def setup(app_paths, args):


	virtual_env = common_funcs.detect_virtual_env(app_paths['root'])
	logging_dir = args.logging_dir if not args.quiet else None
	if not install_mqtttransfer_service(app_paths['root'], virtual_env, logging_dir, args.services_dir):
		return False

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
	parser.add_argument(
		'-s', '--services-dir', 
		help='Directory where WatchTower services files will be stored', 
		default=os.path.join("/","lib","systemd","system")
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