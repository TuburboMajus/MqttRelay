from temod.base.entity import Entity
from temod.base.attribute import *


class DeviceType(Entity):
    ENTITY_NAME = "device_type"
    ATTRIBUTES = [
        {"name":"id","type":IntegerAttribute,"required":True,"is_auto":True,"is_id":True,"is_nullable":False},
        {"name":"vendor","type":StringAttribute,"max_length":128,"required":True,"is_nullable":False},
        {"name":"model","type":StringAttribute,"max_length":128,"required":True,"is_nullable":False},
        {"name":"kind","type":StringAttribute,"max_length":64,"required":True,"is_nullable":False},
        {"name":"capabilities","type":StringAttribute,"is_nullable":False,"default_value":"{}"},  # JSON stored as String
        {"name":"payload_schema","type":StringAttribute,"is_nullable":False,"default_value":"{}"},  # JSON stored as String
        {"name":"defaults_json","type":StringAttribute,"is_nullable":False,"default_value":"{}"},  # JSON stored as String
        {"name":"notes","type":StringAttribute,"max_length":512},
        {"name":"created_at","type":DateTimeAttribute,"required":True,"is_nullable":False}
    ]


class Device(Entity):
    ENTITY_NAME = "device"
    ATTRIBUTES = [
        {"name":"id","type":IntegerAttribute,"required":True,"is_auto":True,"is_id":True,"is_nullable":False},
        {"name":"client_id","type":IntegerAttribute},
        {"name":"device_type_id","type":IntegerAttribute,"required":True,"is_nullable":False},
        {"name":"external_ref","type":StringAttribute,"max_length":128},
        {"name":"name","type":StringAttribute,"max_length":255},
        {"name":"working","type":BooleanAttribute,"is_nullable":False,"default_value":True},
        {"name":"installed","type":BooleanAttribute,"is_nullable":False,"default_value":False},
        {"name":"topic","type":StringAttribute},
        {"name":"metadata_json","type":StringAttribute},  # JSON stored as String
        {"name":"emission_rate","type":IntegerAttribute,"is_nullable":False, "default_value":20*60000},
        {"name":"created_at","type":DateTimeAttribute,"required":True,"is_nullable":False}
    ]

    UPDATABLE_FIELDS = ['device_type_id','external_ref','name',"metadata_json","working","installed","topic"]


class LatestValue(Entity):
    ENTITY_NAME = "latest_value"
    ATTRIBUTES = [
        {"name":"device_id","type":IntegerAttribute,"required":True,"is_id":True,"is_nullable":False},
        {"name":"key_name","type":StringAttribute,"max_length":128,"required":True,"is_id":True,"is_nullable":False},
        {"name":"ts","type":DateTimeAttribute,"required":True,"is_nullable":False},
        {"name":"num_value","type":RealAttribute},
        {"name":"str_value","type":StringAttribute,"max_length":1024},
        {"name":"bool_value","type":IntegerAttribute},
        {"name":"json_value","type":StringAttribute},  # JSON stored as String
        {"name":"unit","type":StringAttribute,"max_length":32},
        {"name":"quality","type":EnumAttribute,"values":["good","suspect","bad"],"required":True,"default_value":"good","is_nullable":False},
        {"name":"meta_json","type":StringAttribute}  # JSON stored as String
    ]