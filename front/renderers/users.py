from flask_login import current_user
from flask import current_app

from temod.base.attribute import StringAttribute

from .base import BaseTemplate




class AuthenticatedUserTemplate(BaseTemplate):
	"""docstring for AuthenticatedUserTemplate"""
	def __init__(self, *args, **kwargs):
		super(AuthenticatedUserTemplate, self).__init__(*args, **kwargs)

	def with_sidebar(self,active_page=None):
		self.kwargs['active_page'] = active_page
		return self

	def with_navbar(self):
		self.kwargs['languages'] = current_app.config['LANGUAGES'].values()
		#notifications = list(Notification.storage.list(user=current_user['id'],orderby="at desc",limit=5))
		#self.kwargs['notifications'] = notifications
		"""
		self.kwargs['unseen_notifications'] = sum([int(not notification['seen']) for notification in notifications])
		self.kwargs['support_id'] = CommonContactAccount.storage.get(
			StringAttribute("name",value="support",owner_name="account")
		)['user']['id']"""
		return self