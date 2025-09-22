from temod.storage.directory import DirectoryStorage
from temod.storage import MysqlEntityStorage
from temod.base.condition import *
from temod.base.attribute import *

from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import importlib
import traceback
import argparse
import logging
import math
import toml
import yaml
import time
import json
import sys
import os


MQTTT_JOB_NAME = "MqttTransfer"
MQTTT_LOG_NAME = "mqttt"


# Function to load configuration from TOML file
def load_configs(root_dir):
	"""Load configuration from config.toml file in the specified root directory"""
	with open(os.path.join(root_dir,"config.toml")) as config_file:
		config = toml.load(config_file)
	return config


# Function to set up logging
def get_logger(logging_dir):
	"""Create and configure a logger with file and console handlers"""
	os.makedirs(logging_dir, exist_ok=True)

	logger = logging.getLogger()
	logger.setLevel(logging.INFO)

	if logger.handlers:
		return logger

	# Set up log message format
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

	# Configure file handler if logging directory is valid
	if logging_dir is not None and os.path.isdir(logging_dir):
		fh = RotatingFileHandler(
			os.path.join(logging_dir,f"{MQTTT_JOB_NAME}.log"),
			maxBytes=5*1024*1024,  # 5MB
			backupCount=3,
			encoding='utf-8'
		) 
		fh.setLevel(logging.INFO)
		fh.setFormatter(formatter)
		logger.addHandler(fh)
	else:
		print("No valid logging directory specified. No logs will be kept.")

	# Configure console handler
	dh = logging.StreamHandler(sys.stdout)
	dh.setLevel(logging.WARNING)
	dh.setFormatter(formatter)
	logger.addHandler(dh)

	return logger


class TopicNotFound(Exception):
	pass
		

class DeviceNotFound(Exception):
	pass
		

class ClientNotFound(Exception):
	pass
		

class MetricNotFound(Exception):
	pass
		

class ParserCodeNotFound(Exception):
	pass
		

class DeviceTypeNotFound(Exception):
	pass
		

class NoRouteFound(Exception):
	pass
		

class DispatcherNotFound(Exception):
	pass
		

class DepositNotFound(Exception):
	pass
		
		

class MqttTransfer(object):

	"""docstring for MqttTransfer"""
	def __init__(self, **mysql_credentials):
		super(MqttTransfer, self).__init__()
		self.mysql_credentials = mysql_credentials
		self.storages = {
			"mqtt_messages":MysqlEntityStorage(entities.MqttMessage,**mysql_credentials),
			"parsers":MysqlEntityStorage(entities.Parser,**mysql_credentials),
			"metrics":MysqlEntityStorage(entities.Metric,**mysql_credentials),
			"parsed_points":MysqlEntityStorage(entities.ParsedPoint,**mysql_credentials),
			"extractions":MysqlEntityStorage(entities.Extraction,**mysql_credentials),
			"clients":MysqlEntityStorage(entities.Parser,**mysql_credentials),
			"topics":MysqlEntityStorage(entities.MqttTopic,**mysql_credentials),
			"devices":MysqlEntityStorage(entities.Device,**mysql_credentials),
			"routes":MysqlEntityStorage(entities.RoutingRule,**mysql_credentials),
			"deposits":MysqlEntityStorage(entities.RouteDeposit,**mysql_credentials),
			"dispatches":MysqlEntityStorage(entities.Dispatch,**mysql_credentials),
			"destinations":MysqlEntityStorage(entities.ClientDestination,**mysql_credentials),
		}
		self.metrics_cache = {}
		self.device_types_cache = {}

	def load_parse_python_function(parser):

		filename = "_".join([parser['name'].lower().replace(" ","_"), parser['version'].lower().replace('.','_')])
		if not PARSERS_DB.has(filename):
			raise ParserCodeNotFound(f"Parser #{parser['id']} code not found (should exist at {os.path.join(PARSERS_DB.directory, filename)})")

		module = importlib.import_module(f"db.parsers.{filename.rsplit('.py',1)[0]}")
		return module.parse

	def load_parse_function(parser):
		if parser['language'].lower() != "python":
			raise LanguageNotHandled(f"The parser #{parser['id']} is coded in an unknown language ({parser['language']})")

		return MqttTransfer.load_parse_python_function(parser)

	def _load_metric(self, metric_id):
		if not metric_id in self.metrics_cache:
			self.metrics_cache[metric_id] = self.storages['metrics'].get(id=metric_id)
			if self.metrics_cache[metric_id] is None:
				raise MetricNotFound(f"Metric #{metric_id} doesn't exist in the database")
		return self.metrics_cache[metric_id]

	def _load_device_type(self, device_type_id):
		if not device_type_id in self.device_types_cache:
			self.device_types_cache[device_type_id] = self.storages['metrics'].get(id=device_type_id)
			if self.device_types_cache[device_type_id] is None:
				raise DeviceTypeNotFound(f"Device Type #{device_type_id} doesn't exist in the database")
		return self.device_types_cache[device_type_id]

	def judge_data_quality(self, *args, **kwargs):
		# TODO
		return "good"

	def retrieve_sender(self, message):
		topic = self.storages['topics'].get(topic=message['topic'],active=True)
		if topic is None:
			topic = self.storages['topics'].get(topic=message['topic'])
			if topic is None:
				raise TopicNotFound(f"Message has been published to an unknown topic {message['topic']}")
			raise DisabledTopic(f"Message has been published to a disabled topic {message['topic']} (topic: #{topic['id']})")

		device = self.storages['devices'].get(id=topic['device_id'])
		if device is None:
			raise DeviceNotFound(f"Topic {message['topic']} is not linked to any device")

		client = self.storages['clients'].get(id=topic['client_id'])
		if client is None:
			raise ClientNotFound(f"Topic {message['topic']} is not linked to any client")

		return topic, device, client

	def select_route(self, client, device, topic, message):

		candidates = []
		evaluated = {}
		for route in self.storages['routes'].list(Or(Equals(IntegerAttribute("device_id",value=device['id'])),Equals(IntegerAttribute("device_id"))),client_id=client['id'], topic_id=topic['id'], active=True):
			context = {
				"device":device.to_dict(), "device_type": self._load_device_type(device['device_type_id']).to_dict(), "topic": topic.to_dict(),"message": message.to_dict()
			}
			if route['conditions'] is not None and route['conditions'].strip() != "":
				try:
					evaluation = eval_mongo_dsl(route['conditions'], **context)
					if not eval_mongo_dsl(route['conditions'], **context):
						continue
					evaluated[route['id']] = 1
				except:
					LOGGER.warning(f"condition in route {route['id']} has failed to be evaulated for context {json.dumps(context)}. Route will be considered conditionless and its priority will be decreased.")
					evaluated[route['id']] = -1
			candidates.append(route)

		prioritary = []
		if len(candidates):
			prioritary = [candidate for candidate in candidates if candidate['priority'] == min([c['priority'] for c in candidates])]
			prioritary = [candidate for candidate in prioritary if candidate['priority']-evaluated.get(candidate['id'],0) == min([c['priority']-evaluated.get(candidate['id'],0) for c in prioritary])]

		prioritary = sorted(prioritary, key=lambda x:x['created_at'], reverse=True)
		if len(prioritary) > 1:
			LOGGER.warning(f"Multiple routes are possible for message #{message['id']} ({','.join(['route #'+str(route['id']) for route in prioritary])}). Newest one will be selected")
		elif len(prioritary) == 0:
			raise NoRouteFound(f"No route found to manage message #{message['id']}")

		selected = prioritary[0]
		LOGGER.info(f"Route #{route['id']} has been selected for message #{message['id']}")

		try:
			json.loads(selected['parser_config'] or "{}")
		except:
			raise ValueError(f"The parser configuration of route #{selected['id']} ({selected['parser_config']}) should be in json format")
		return selected

	def process_message(self, message):
		extraction = {"id":self.storages['extractions'].generate_value('id'),"message_id":message['id'], "parsed_at":datetime.now(), "success":True}

		topic, device, client = self.retrieve_sender(message)
		LOGGER.info(f"{message['id']} sent by device #{device['id']} of client {client['name']} (#{client['id']})")

		route = self.select_route(client, device, topic, message)
		LOGGER.info(f"route (#{route['id']}) selected for message #{message['id']}")

		parser = self.storages['parsers'].get(id=route['parser_id'])
		LOGGER.info(f"{parser['name']} selected for message #{message['id']}")

		extraction['parser_id'] = parser['id']
		extraction['parser_config'] = route['parser_config']

		parse_function = MqttTransfer.load_parse_function(parser)

		results = parse_function(json.loads(message['payload']) if type(message['payload']) is str else message['payload'], **json.loads(route['parser_config'] or "{}"))

		if not results:
			extraction['error'] = f"Parsing function didn't return any result for message #{message['id']}: {json.dumps(message['payload'])}"
			LOGGER.warning(extraction['error'])
			extraction['success'] = False
		else:
			extraction['extracted_count'] = len(results)

		ts = message['at']
		if "at" in (results or {}):
			ts = results['at']

		parsed = []
		for metric_id, value in (results or {}).items():
			if not (type(metric_id) is int):
				continue
			metric = self._load_metric(metric_id)
			transformer = lambda x: x
			if type(value) in [int, float]:
				value_field = "num_value"
			elif type(value) is str:
				value_field = "str_value"
			elif type(value) is bool:
				value_field = "bool_value"
			elif type(value) in [dict, list]:
				value_field = "json_value"
				transformer = lambda x: json.dumps(x)
			parsed.append(entities.ParsedPoint(
				id=-1, extraction_id=extraction['id'],device_id=device['id'],metric_id=metric_id, ts=ts, unit=metric['default_unit'], quality=self.judge_data_quality(
					metric, value
				), meta_json=json.dumps({k:v for k,v in results.items() if not type(k) is int}),**{value_field:transformer(value)}
			))

		return parsed, entities.Extraction(**extraction), route


	def on_data_sent(self, dispatch, **kwargs):
		dispatch.takeSnapshot()
		dispatch.setAttributes(**kwargs)
		self.storages['dispatches'].updateOnSnapshot(dispatch)
		return dispatch["status"].name == "sent"


	def dispatch_to_deposit(self, deposit, extraction, data_points):
		destination = self.storages['destinations'].get(id=deposit['destination_id'])
		if destination is None:
			raise DestinationNotFound(f"Client destination #{deposit['destination_id']} not found")

		dispatch = entities.Dispatch(
			id=self.storages['dispatches'].generate_value('id'),extraction_id=extraction['id'],destination_id=destination['id'],rule_id=deposit['rule_id'],
			status="queued", created_at=datetime.now(), attempts=1
		)
		self.storages['dispatches'].create(dispatch.takeSnapshot())

		dispatcher_class = DISPATCHERS.get(destination['type'].name.lower())
		if dispatcher_class is None:
			raise DispatcherNotFound(f"The dispatcher for data to client destinations of type {destination['type'].name} is not implemented")

		dispatcher = dispatcher_class(
			**{k:v for k,v in destination.to_dict().items() if k != "options_json"},
			**(json.loads(destination['options_json']) if type(destination['options_json']) is str else destination['options_json'])
		)
		LOGGER.info(f"Dispatcher of type {dispatcher_class.__name__} has been loaded and initialized successfully")
		is_asynchronous = getattr(dispatcher,'asynchronous',False)
		if is_asynchronous:
			dispatcher.setCallback(lambda *x,**y: self.on_data_sent(deposit, *x, **y))

		try:
			results = dispatcher.dispatch(parsed_points=[dp.to_dict() for dp in data_points])
		except:
			LOGGER.warning(f"Dispatch has failed")
			LOGGER.warning(traceback.format_exc())
			results = {"status":"failed", "response_snippet": traceback.format_exc()}

		if not is_asynchronous:
			return self.on_data_sent(dispatch, **results)

		return True


	def send_parsed_data(self, route, extraction, data_points):

		dispatched = []
		deposits = list(self.storages['deposits'].list(rule_id=route['id']))
		if len(deposits) == 0:
			raise DepositNotFound(f"No client destination found for routing rule #{route['id']}")

		for deposit in deposits:
			LOGGER.info(f"Sending {len(data_points)} points of data  from extraction #{extraction['id']} to deposit (rule: #{deposit['rule_id']} - destination {deposit['destination_id']})")
			try:
				dispatched.append(self.dispatch_to_deposit(deposit, extraction, data_points))
				if not dispatched[-1]:
					LOGGER.warning(f"Dispatch to deposit (rule: #{deposit['rule_id']} - destination {deposit['destination_id']}) for extraction #{extraction['id']} didn't end with success")
			except:
				LOGGER.error(f"Error while dispatching data of extraction #{extraction['id']} to destination {deposit['destination_id']}")
				LOGGER.error(traceback.format_exc())
				dispatched.append(False)

		return all(dispatched)


	def process(self, directory):

		data_treated = []
		to_treat = list(self.storages['mqtt_messages'].list(processed=False))
		LOGGER.info(f"{len(to_treat)} mqtt messages unprocessed")
		for mqtt_message in to_treat:
			try:

				points, extraction, route = self.process_message(mqtt_message)
				self.storages['extractions'].create(extraction)
				for point in points:
					self.storages['parsed_points'].create(point)
				
				if not extraction['success']:
					data_treated.append(False); continue

				sent = self.send_parsed_data(route, extraction, points)
				mqtt_message.takeSnapshot()['processor'] = extraction['id']
				if sent:
					mqtt_message["processed"] =True
				self.storages['mqtt_messages'].updateOnSnapshot(mqtt_message)

				data_treated.append(sent)

			except:
				LOGGER.error(f"Error while processing mqtt mqtt_message {json.dumps(mqtt_message.to_dict())}")
				LOGGER.error(traceback.format_exc())
				data_treated.append(False)

		return all(data_treated)


def already_running(**mysql_credentials):
	MqttTransferJob = MysqlEntityStorage(entities.Job, **mysql_credentials).get(name=MQTTT_JOB_NAME)
	if MqttTransferJob['state'] == "RUNNING":
		return True
	return False

def start_run(**mysql_credentials):
	storage = MysqlEntityStorage(entities.Job, **mysql_credentials)
	MqttTransferJob = storage.get(name=MQTTT_JOB_NAME).takeSnapshot()
	MqttTransferJob.setAttribute("state","RUNNING")
	storage.updateOnSnapshot(MqttTransferJob)

def stop_run(exit_code, **mysql_credentials):
	storage = MysqlEntityStorage(entities.Job, **mysql_credentials)
	MqttTransferJob = storage.get(name=MQTTT_JOB_NAME).takeSnapshot()
	MqttTransferJob.setAttribute("state","IDLE")
	MqttTransferJob.setAttribute("last_exit_code",exit_code)
	storage.updateOnSnapshot(MqttTransferJob)
	if exit_code != 0:
		sys.exit(exit_code)

def launch(config):
	if already_running(**config["storage"]["credentials"]):
		LOGGER.info("Mqtt Transfer job is already ongoing. Postponing execution.")
		return
	start_run(**config["storage"]["credentials"])

	mqttt = MqttTransfer(**config["storage"]["credentials"])

	results = mqttt.process(PARSERS_DB_FOLDER)	
	exit_code=0	
	if results is not None:
		if results:
			LOGGER.info("All new data treated successfully.")
		else:
			LOGGER.warning("Some data wasn't treated successfully.")
			exit_code=2
	return exit_code


if __name__ == "__main__":
	""" Defining and parsing args """
	parser = argparse.ArgumentParser(prog="Parses and transfers data incomming through mqtt to clients")

	parser.add_argument('-r', '--root-dir', help='Mqtt Relay root directory', default=".")
	parser.add_argument('-l', '--logging-dir', help='Directory where to store logs.', default=None)

	args = parser.parse_args()

	if args.root_dir:
		if not os.path.isdir(args.root_dir):
			print(f"Root directory path must be a valid directory.")
			sys.exit(1)
		if not args.root_dir in sys.path:
			sys.path.append(args.root_dir)
	else:
		sys.exit(1)

	PARSERS_DB_FOLDER = os.path.join(args.root_dir,"db","parsers")
	if not os.path.isdir(PARSERS_DB_FOLDER):
		os.mkdir(PARSERS_DB_FOLDER)

	PARSERS_DB = DirectoryStorage(PARSERS_DB_FOLDER)

	setattr(__builtins__,'LOGGER', get_logger(args.logging_dir))
	
	from services.mqtt_transfer.dispatchers import DISPATCHERS
	from tools.json_conditions import eval_mongo_dsl
	import core.entity as entities

	config = load_configs(args.root_dir)

	try:
		exit_code = launch(config)
	except:
		LOGGER.error("Mqtt Transfer failed with error. Traceback:")
		LOGGER.error(traceback.format_exc())
		stop_run(1,**config["storage"]["credentials"])
	else:
		stop_run(exit_code,**config["storage"]["credentials"])