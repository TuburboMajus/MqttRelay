# ** Section ** Imports
from temod.base.condition import *
from temod.base.attribute import *
from temod.base.join import *

from core.constraints import *
# ** EndSection ** Imports

# ** Section ** Join_RouteFile
class RoutingRuleFile(Join):

	DEFAULT_ENTRY = RoutingRule

	STRUCTURE = [
		CSTR_ROUTE_TOPIC(),
		CSTR_ROUTE_CLIENT(),
		CSTR_ROUTE_DEVICE(multiplicity=Multiplicity(start=1,end=0)),
		CSTR_ROUTE_PARSER()
	]
# ** EndSection ** Join_RouteFile

# ** Section ** Join_RouteDepositDetails
class RouteDepositDetails(Join):

	DEFAULT_ENTRY = RouteDeposit

	STRUCTURE = [
		CSTR_DEPOSIT_DESTINATION()
	]
# ** EndSection ** Join_RouteDepositDetails