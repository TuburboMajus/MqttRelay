# ** Section ** Imports
from temod.base.entity import Entity
from temod.base.attribute import *
from copy import deepcopy
# ** EndSection ** Imports


# ** Section ** Entity_User
class User(Entity):
	ENTITY_NAME = "user"
	ATTRIBUTES = [
		{"name":"id","type":UUID4Attribute,"required":True,"is_id":True,"is_nullable":False},
		{"name":"privilege","type":UUID4Attribute,"required":True,"is_nullable":False},
		{"name":"email","type":StringAttribute,"required":True, "max_length": 100, "is_nullable":False},
		{"name":"password","type":BCryptedAttribute},
		{"name":"is_authenticated","type":BooleanAttribute,"is_nullable":False,"default_value":False},
		{"name":"is_active","type":BooleanAttribute,"is_nullable":False,"default_value":False},
		{"name":"is_disabled","type":BooleanAttribute,"is_nullable":False,"default_value":False},
		{"name":"language","type":StringAttribute,"non_empty":True,"is_nullable":False,"default_value":"fr"}
	]
# ** EndSection ** Entity_User

# ** Section ** Entity_Privilege
class Privilege(Entity):
	ENTITY_NAME = "privilege"
	ATTRIBUTES = [
		{"name":"id","type":UUID4Attribute,"required":True,"is_id":True,"is_nullable":False},
		{"name":"label","type":StringAttribute,"required":True,"non_empty":True,"is_nullable":False},
		{"name":"roles","type":StringAttribute,"required":True,"non_empty":True,"is_nullable":False}
	]
# ** EndSection ** Entity_Privilege
