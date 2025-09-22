# ** Section ** Imports
from temod.base.condition import *
from temod.base.attribute import *
from temod.base.join import *

from core.constraints import *
# ** EndSection ** Imports

# ** Section ** Join_MqttMessageTopic
class MqttMessageTopic(Join):

	DEFAULT_ENTRY = MqttMessage

	STRUCTURE = [
		CSTR_MQTT_MESSAGE_TOPIC(multiplicity=Multiplicity(start=1, end=0))
	]
# ** EndSection ** Join_MqttMessageTopic

# ** Section ** Join_MqttMessageTopic
class MqttTopicFile(Join):

	DEFAULT_ENTRY = MqttTopic

	STRUCTURE = [
		CSTR_MQTT_TOPIC_CLIENT(multiplicity=Multiplicity(start=1, end=0)),
		CSTR_MQTT_TOPIC_DEVICE(multiplicity=Multiplicity(start=1, end=0)),
	]
# ** EndSection ** Join_MqttMessageTopic