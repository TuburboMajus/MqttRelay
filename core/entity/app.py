# ** Section ** Imports
from temod.base.entity import Entity
from temod.base.attribute import *
from copy import deepcopy
# ** EndSection ** Imports


# ** Section ** Entity_MqttRelay
class MqttRelay(Entity):
	ENTITY_NAME = "mqtt_relay"
	ATTRIBUTES = [
		{"name":"version","type":StringAttribute, "max_length":20, "required":True,"is_id":True,"non_empty":True,"is_nullable":False},
	]
# ** EndSection ** Entity_DigiUpAgri
