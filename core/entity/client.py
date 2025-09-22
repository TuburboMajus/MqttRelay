from temod.base.entity import Entity
from temod.base.attribute import *


class Client(Entity):
	ENTITY_NAME = "client"
	ATTRIBUTES = [
		{"name":"id","type":IntegerAttribute,"required":True,"is_id":True,"is_auto":True,"is_nullable":False},
		{"name":"slug","type":StringAttribute,"max_length":64,"required":True,"is_nullable":False},
		{"name":"name","type":StringAttribute,"max_length":255,"required":True,"is_nullable":False},
		{"name":"contact_email","type":StringAttribute,"max_length":255},
		{"name":"phone","type":StringAttribute,"max_length":255},
		{"name":"status","type":EnumAttribute,"values":["active","paused","disabled"],"required":True,"default_value":"active","is_nullable":False},
		{"name":"created_at","type":DateTimeAttribute,"required":True,"is_nullable":False}
	]

	UPDATABLE_FIELDS = ['name','contact_email',"phone","status"]


class ClientDestination(Entity):
	ENTITY_NAME = "client_destination"
	ATTRIBUTES = [
		{"name":"id","type":IntegerAttribute,"required":True,"is_id":True,"is_auto":True,"is_nullable":False},
		{"name":"client_id","type":IntegerAttribute,"required":True,"is_nullable":False},
		{"name":"type","type":EnumAttribute,"values":["mysql","postgres","http","kafka","file","other"],"required":True,"is_nullable":False},
		{"name":"host","type":StringAttribute,"max_length":255},
		{"name":"port","type":IntegerAttribute},
		{"name":"database_name","type":StringAttribute,"max_length":255},
		{"name":"username","type":StringAttribute,"max_length":255},
		{"name":"password_enc","type":BytesAttribute,"max_length":1024},
		{"name":"encryption_version","type":StringAttribute},
		{"name":"uri","type":StringAttribute,"max_length":1024},
		{"name":"options_json","type":StringAttribute},  # JSON stored as String
		{"name":"active","type":IntegerAttribute,"required":True,"default_value":1,"is_nullable":False},
		{"name":"created_at","type":DateTimeAttribute,"required":True,"is_nullable":False}
	]

	UPDATABLE_FIELDS = ['type','host',"port","database_name","username","password_enc","uri","options_json","active"]


class RoutingRule(Entity):
	ENTITY_NAME = "routing_rule"
	ATTRIBUTES = [
		{"name":"id","type":UUID4Attribute,"required":True,"is_id":True,"is_nullable":False},
		{"name":"client_id","type":IntegerAttribute,"required":True,"is_nullable":False},
		{"name":"topic_id","type":IntegerAttribute},
		{"name":"device_id","type":IntegerAttribute},
		{"name":"parser_id","type":IntegerAttribute},
		{"name":"parser_config","type":StringAttribute},  # JSON stored as String
		{"name":"active","type":IntegerAttribute,"required":True,"default_value":1,"is_nullable":False},
		{"name":"priority","type":IntegerAttribute,"required":True,"default_value":100,"is_nullable":False},
		{"name":"conditions","type":StringAttribute},  # JSON stored as String
		{"name":"created_at","type":DateTimeAttribute,"required":True,"is_nullable":False}
	]

	UPDATABLE_FIELDS = ['client_id','topic_id',"device_id","parser_id","parser_config","active","priority","conditions"]


class RouteDeposit(Entity):
	ENTITY_NAME = "route_deposit"
	ATTRIBUTES = [
		{"name":"rule_id","type":UUID4Attribute,"required":True,"is_id":True,"is_nullable":False},
		{"name":"destination_id","type":IntegerAttribute,"required":True,"is_id":True,"is_nullable":False},
	]

	UPDATABLE_FIELDS = []


class Dispatch(Entity):
	ENTITY_NAME = "dispatch"
	ATTRIBUTES = [
		{"name":"id","type":UUID4Attribute,"required":True,"is_id":True,"is_nullable":False},
		{"name":"extraction_id","type":UUID4Attribute,"required":True,"is_nullable":False},
		{"name":"destination_id","type":IntegerAttribute,"required":True,"is_nullable":False},
		{"name":"rule_id","type":UUID4Attribute,"required":True,"is_nullable":False},
		{"name":"status","type":EnumAttribute,"values":["queued","sent","failed","retrying","dead"],"required":True,"default_value":"queued","is_nullable":False},
		{"name":"http_status","type":IntegerAttribute},
		{"name":"response_snippet","type":StringAttribute},
		{"name":"attempts","type":IntegerAttribute,"required":True,"default_value":0,"is_nullable":False},
		{"name":"next_retry_at","type":DateTimeAttribute},
		{"name":"sent_at","type":DateTimeAttribute},
		{"name":"created_at","type":DateTimeAttribute,"required":True,"is_nullable":False},
		{"name":"updated_at","type":DateTimeAttribute}
	]
