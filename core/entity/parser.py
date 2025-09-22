from temod.base.entity import Entity
from temod.base.attribute import *

class Parser(Entity):
    ENTITY_NAME = "parser"
    ATTRIBUTES = [
        {"name":"id","type":IntegerAttribute,"required":True,"is_id":True,"is_auto":True,"is_nullable":False},
        {"name":"name","type":StringAttribute,"max_length":128,"required":True,"is_nullable":False},
        {"name":"version","type":StringAttribute,"max_length":32,"required":True,"is_nullable":False},
        {"name":"description","type":StringAttribute,"max_length":512},
        {"name":"language","type":StringAttribute,"max_length":32},
        {"name":"config_schema","type":StringAttribute},  # JSON stored as String
        {"name":"active","type":IntegerAttribute,"required":True,"default_value":1,"is_nullable":False}
    ]

    UPDATABLE_FIELDS = ['name','version',"description","language","config_schema","active"]
    FILE_EXTENSIONS = {
        "python":"py", "javascript":"js", "bash": "sh"
    }

class Extraction(Entity):
    ENTITY_NAME = "extraction"
    ATTRIBUTES = [
        {"name":"id","type":UUID4Attribute,"required":True,"is_id":True,"is_nullable":False},
        {"name":"message_id","type":IntegerAttribute,"required":True,"is_nullable":False},
        {"name":"parser_id","type":IntegerAttribute,"required":True,"is_nullable":False},
        {"name":"parser_config","type":StringAttribute},  # JSON stored as String
        {"name":"parsed_at","type":DateTimeAttribute,"required":True,"is_nullable":False},
        {"name":"success","type":IntegerAttribute,"required":True,"is_nullable":False},
        {"name":"error_text","type":StringAttribute},
        {"name":"extracted_count","type":IntegerAttribute,"required":True,"default_value":0,"is_nullable":False}
    ]

class Metric(Entity):
    ENTITY_NAME = "metric_catalog"
    ATTRIBUTES = [
        {"name":"id","type":IntegerAttribute,"required":True,"is_id":True,"is_auto":True,"is_nullable":False},
        {"name":"key_name","type":StringAttribute,"max_length":128,"required":True,"is_nullable":False},
        {"name":"default_unit","type":StringAttribute,"max_length":32},
        {"name":"description","type":StringAttribute,"max_length":512},
        {"name":"digiupagri_ref","type":StringAttribute,"max_length":3,"required":True,"is_nullable":False},
    ]

    UPDATABLE_FIELDS = ["key_name","default_unit","description","digiupagri_ref"]

class ParsedPoint(Entity):
    ENTITY_NAME = "parsed_point"
    ATTRIBUTES = [
        {"name":"id","type":IntegerAttribute,"required":True,"is_id":True,"is_auto":True,"is_nullable":False},
        {"name":"extraction_id","type":UUID4Attribute,"required":True,"is_nullable":False},
        {"name":"device_id","type":IntegerAttribute},
        {"name":"metric_id","type":IntegerAttribute},
        {"name":"ts","type":DateTimeAttribute,"required":True,"is_nullable":False},
        {"name":"num_value","type":RealAttribute},
        {"name":"str_value","type":StringAttribute,"max_length":1024},
        {"name":"bool_value","type":IntegerAttribute},
        {"name":"json_value","type":StringAttribute},  # JSON stored as String
        {"name":"unit","type":StringAttribute,"max_length":32},
        {"name":"quality","type":EnumAttribute,"values":["good","suspect","bad"],"required":True,"default_value":"good","is_nullable":False},
        {"name":"meta_json","type":StringAttribute}  # JSON stored as String
    ]

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