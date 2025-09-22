# ** Section ** Imports
from temod.base.condition import *
from temod.base.attribute import *
from temod.base.join import *

from core.constraints import *
# ** EndSection ** Imports

# ** Section ** Join_DeviceFile
class DeviceFile(Join):

	DEFAULT_ENTRY = Device

	STRUCTURE = [
		CSTR_DEVICE_DEVICE_TYPE()
	]
# ** EndSection ** Join_DeviceFile

# ** Section ** Join_DeviceTopic
class DeviceTopic(Join):

	DEFAULT_ENTRY = Device

	STRUCTURE = [
		CSTR_DEVICE_DEVICE_TYPE(),
		CSTR_DEVICE_TOPIC(multiplicity=Multiplicity(start=1,end=0))
	]
# ** EndSection ** Join_DeviceTopic