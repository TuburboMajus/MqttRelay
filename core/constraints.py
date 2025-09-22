from temod.base.constraint import *
from .entity import *


############## USER ###################
class CSTR_USER_PRIVILEGE(EqualityConstraint):
	ATTRIBUTES = [
		{"name":"id","entity":Privilege},
		{"name":"privilege","entity":User},
	]


############## IOT ###################
class CSTR_DEVICE_DEVICE_TYPE(EqualityConstraint):
	ATTRIBUTES = [
		{"name":"id","entity":DeviceType},
		{"name":"device_type_id","entity":Device},
	]
class CSTR_DEVICE_TOPIC(EqualityConstraint):
	ATTRIBUTES = [
		{"name":"topic","entity":MqttTopic},
		{"name":"topic","entity":Device},
	]


############## MQTT ###################
class CSTR_MQTT_MESSAGE_TOPIC(EqualityConstraint):
	ATTRIBUTES = [
		{"name":"topic","entity":MqttTopic},
		{"name":"topic","entity":MqttMessage},
	]

class CSTR_MQTT_TOPIC_CLIENT(EqualityConstraint):
	ATTRIBUTES = [
		{"name":"device_id","entity":MqttTopic},
		{"name":"id","entity":Device},
	]

class CSTR_MQTT_TOPIC_DEVICE(EqualityConstraint):
	ATTRIBUTES = [
		{"name":"client_id","entity":MqttTopic},
		{"name":"id","entity":Client},
	]


############## ROUTES ###################
class CSTR_ROUTE_TOPIC(EqualityConstraint):
	ATTRIBUTES = [
		{"name":"id","entity":MqttTopic},
		{"name":"topic_id","entity":RoutingRule},
	]

class CSTR_ROUTE_CLIENT(EqualityConstraint):
	ATTRIBUTES = [
		{"name":"id","entity":Client},
		{"name":"client_id","entity":RoutingRule},
	]

class CSTR_ROUTE_DEVICE(EqualityConstraint):
	ATTRIBUTES = [
		{"name":"id","entity":Device},
		{"name":"device_id","entity":RoutingRule},
	]

class CSTR_ROUTE_PARSER(EqualityConstraint):
	ATTRIBUTES = [
		{"name":"id","entity":Parser},
		{"name":"parser_id","entity":RoutingRule},
	]

class CSTR_DEPOSIT_DESTINATION(EqualityConstraint):
	ATTRIBUTES = [
		{"name":"id","entity":ClientDestination},
		{"name":"destination_id","entity":RouteDeposit},
	]
		
