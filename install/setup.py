from temod.storage.mysql import MysqlEntityStorage
from subprocess import Popen, PIPE, STDOUT
from pathlib import Path
from uuid import uuid4 

from temod.base.attribute import *

import sys
import os

if not os.getcwd() in sys.path:
	sys.path.append(os.getcwd())

from install import common_funcs
from datetime import datetime
from getpass import getpass
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

def get_admin_user():
	print("\n\nAdmin account setup")
	email = None
	while email is None:
		email = input("Provide the admin email: ")
		try:
			email = EmailAttribute("",value=email).value
		except:
			print("Wrong email format. Try again")
			email = None

	password = None
	while password is None:
		password = getpass("Provide the admin password: ")
		cpassword = getpass("Confirm the admin password: ")
		if len(password) == 0 or password != cpassword:
			password = None
			print("Passwords do not match or are empty. Provide a valid password.")
	
	return {"email":email,"password":password}


def get_mqtt_broker():
	print("\n\nMqtt broker setup")
	"""Ask the user for MQTT configuration values via terminal input."""
	config = {}

	config["broker_url"] = input("\n\nEnter broker URL [localhost]: ") or "localhost"
	config["broker_port"] = int(input("Enter broker port [1883]: ") or 1883)
	config["username"] = input("Enter username (leave empty for none): ")
	config["password"] = input("Enter password (leave empty for none): ")
	config["keepalive"] = int(input("Enter keepalive [0]: ") or 0)

	tls_input = input("Enable TLS? (yes/*) [no]: ").strip().lower()
	config["tls_enabled"] = tls_input in ("yes", "y", "true", "1")

	print("You can later change the settings from config.toml")

	return config


def get_crypto_config():
	print("\n\nCrypto configuration")
	key_source = None
	while key_source is None:
		key_source = input("Where would you like to store the master keys that decode the secrets in your db (0: env, 1: database) [env recommended]: ").strip().lower()
		if not (key_source in ["1","0","env","db","database"]):
			print("Invalid choice. Try again")
			key_source = None
		else:
			try:
				key_source = ["env","db"][int(key_source)]
			except:
				key_source = {"database":"db"}.get(key_source,key_source)

	key = None
	while key is None:
		key = input("Provide your own master key (base64 encoding of a 32 bits key) or leave empty to generate a random one: ").strip().lower()
		if key == "":
			key = base64.b64encode(os.urandom(32))
		else:
			try:
				assert(len(base64.b64decode(key.encode())) == 32)
			except:
				key = None
				print('The specified key has the wrong format')

	if key_source == "env":
		print(""" Atention ! Since you've chosen env as key source, the master key will be saved into .env at the root of MqttRelay. 
If you find this method not secure enough, which it is, remove the key from there and set it in the environment on your own""")

	return {"key_source":key_source, "key":key}


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


def install_preset_objects(credentials, admin_user, crypto_config):	

	mqtt_relay = MqttRelay(version=APP_VERSION)
	crypto_config = CryptoConfig(id=1, algorithm="aes-256-gcm",key_source=crypto_config['key_source'],key_id="PRIMARY",iv_bytes=12, tag_bytes=16, encoding="base64", version=1,updated_at=datetime.now())
	if crypto_config['key_source'] == "db":
		MysqlEntityStorage(CryptoKey,**credentials).create(CryptoKey(key_id="PRIMARY",version=1,key_b64=crypto_config['key']),updated_at=datetime.now())
	
	user_storage = MysqlEntityStorage(User,**credentials)
	privilege_storage = MysqlEntityStorage(Privilege,**credentials)

	admin_privilege = Privilege(privilege_storage.generate_value('id'),label="admin",roles="*")
	user = User(id=user_storage.generate_value('id'),privilege=admin_privilege['id'],**{k:v for k,v in admin_user.items() if k != "password"})
	user['password'] = admin_user['password']

	MysqlEntityStorage(MqttRelay,**credentials).create(mqtt_relay)
	MysqlEntityStorage(Language, **credentials).create(Language(code="fr",name="français"))
	MysqlEntityStorage(CryptoConfig, **credentials).create(crypto_config)
	privilege_storage.create(admin_privilege)
	user_storage.create(user)

	return True


def setup(app_paths, args):


	virtual_env = common_funcs.detect_virtual_env(app_paths['root'])
	logging_dir = args.logging_dir if not args.quiet else None
	if not install_mqtttransfer_service(app_paths['root'], virtual_env, logging_dir, args.services_dir):
		return False

	credentials = common_funcs.get_mysql_credentials()
	admin_user = get_admin_user()
	mqtt_broker = get_mqtt_broker()
	crypto_config = get_crypto_config()

	already_created = search_existing_database(credentials)
	if already_created:
		if not confirm_database_overwrite():
			LOGGER.warning("If you which to just update the app, run the script install/update.py")
			return False

	with open(app_paths['mysql_schema_file']) as file:
		if not common_funcs.execute_mysql_script(credentials, file.read().replace("$database",credentials['database'])):
			return False

	template_config = common_funcs.load_toml_config(app_paths['template_config_file'])
	template_config["mqtt"].update(mqtt_broker)
	template_config['storage']['credentials'].update(credentials)
	common_funcs.save_toml_config(template_config, app_paths['config_file'])

	if crypto_config['key_source'] == "env":
		with open(".env","w") as file:
			file.write(f"MQTT_RELAY_ENC_KEY_PRIMARY = {crypto_config['key']}")

	return install_preset_objects(credentials, admin_user, crypto_config)


if __name__ == "__main__":

	print("\n"); width = common_funcs.print_pattern("MqttRelay Server"); print(); print("#"*width); print()

	parser = argparse.ArgumentParser(prog="Installs a MqttRelay server")
	parser.add_argument(
		'-l', '--logging-dir', help='Directory where log files will be stored', 
		default=os.path.join("/","var","log","mqtt_relay")
	)
	parser.add_argument(
		'-s', '--services-dir', 
		help='Directory where MqttRelay services files will be stored', 
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