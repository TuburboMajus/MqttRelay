# ** Section ** Imports
from temod.base.condition import *
from temod.base.attribute import *
from temod.base.join import *

from core.entity.user import *

from core.constraints import *
# ** EndSection ** Imports

# ** Section ** Join_UserAccount
class UserAccount(Join):

	DEFAULT_ENTRY = User

	STRUCTURE = [
		CSTR_USER_PRIVILEGE()
	]

	EXO_SKELETON = {
		"is_authenticated":"user.is_authenticated",
		"is_active":"user.is_active",
		"id":"user.id",
	}
# ** EndSection ** Join_UserAccount