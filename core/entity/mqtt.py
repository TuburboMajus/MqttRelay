# ** Section ** Imports
from temod.base.entity import Entity
from temod.base.attribute import *
from copy import deepcopy
# ** EndSection ** Imports



# ** Section ** Entity_MqttMessage
class MqttMessage(Entity):
	ENTITY_NAME = "mqtt_messages"
	ATTRIBUTES = [
		{"name":"id","type":IntegerAttribute, "required":True,"is_id":True, "is_auto":True, "is_nullable":False},
		{"name":"client","type":StringAttribute, "max_length":255, "required":True,"is_nullable":False},
		{"name":"topic","type":StringAttribute, "max_length":255, "required":True,"is_nullable":False},
		{"name":"payload","type":StringAttribute},
		{"name":"qos","type":IntegerAttribute, "is_nullable":False, "default_value": 0},
		{"name":"at","type":DateTimeAttribute, "required":True,"is_nullable":False}
	]
# ** EndSection ** Entity_DataMetric