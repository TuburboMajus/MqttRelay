# ** Section ** Imports
from temod.base.entity import Entity
from temod.base.attribute import *
from copy import deepcopy
# ** EndSection ** Imports



# ** Section ** Entity_MqttMessage
class MqttMessage(Entity):
	ENTITY_NAME = "mqtt_message"
	ATTRIBUTES = [
		{"name":"id","type":IntegerAttribute, "required":True,"is_id":True, "is_auto":True, "is_nullable":False},
		{"name":"client","type":StringAttribute, "max_length":255, "required":True,"is_nullable":False},
		{"name":"topic","type":StringAttribute, "max_length":255, "required":True,"is_nullable":False},
		{"name":"payload","type":StringAttribute},
        {"name":"qos","type":IntegerAttribute, "is_nullable":False, "default_value": 0},
        {"name":"processed","type":BooleanAttribute, "is_nullable":False, "default_value": 0},
        {"name":"processor","type":UUID4Attribute},
		{"name":"at","type":DateTimeAttribute, "required":True,"is_nullable":False}
	]
# ** EndSection ** Entity_MqttMessage


# ** Section ** Entity_MqttTopic
class MqttTopic(Entity):
    ENTITY_NAME = "mqtt_topic"
    ATTRIBUTES = [
        {"name":"id","type":IntegerAttribute,"required":True,"is_auto":True,"is_id":True,"is_nullable":False},
        {"name":"topic","type":StringAttribute,"max_length":255,"required":True,"is_nullable":False},
        {"name":"description","type":StringAttribute,"max_length":512},
        {"name":"qos_default","type":IntegerAttribute,"default_value":0},
        {"name":"active","type":IntegerAttribute,"required":True,"default_value":1,"is_nullable":False},
        {"name":"client_id","type":IntegerAttribute},
        {"name":"device_id","type":IntegerAttribute},
        {"name":"created_at","type":DateTimeAttribute,"required":True,"default_value":"CURRENT_TIMESTAMP","is_nullable":False}
    ]
    
    UPDATABLE_FIELDS = ['qos_default','active',"client_id","device_id"]
# ** EndSection ** Entity_MqttTopic


# ** Section ** Entity_MqttBroker
class MqttBroker(Entity):
    ENTITY_NAME = "mqtt_broker"
    ATTRIBUTES = [
        {"name":"id","type":IntegerAttribute,"required":True,"is_auto":True,"is_id":True,"is_nullable":False},
        {"name":"name","type":StringAttribute,"max_length":128,"required":True,"is_nullable":False},
        {"name":"uri","type":StringAttribute,"max_length":512,"required":True,"is_nullable":False},
        {"name":"client_id","type":IntegerAttribute},
        {"name":"auth_json","type":StringAttribute},  # JSON stored as String
        {"name":"last_seen_at","type":DateTimeAttribute},
        {"name":"active","type":IntegerAttribute,"required":True,"default_value":1,"is_nullable":False}
    ]
# ** EndSection ** Entity_MqttBroker