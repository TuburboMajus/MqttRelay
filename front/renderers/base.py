from flask import g, render_template, request
from pathlib import Path



class BaseTemplate(object):
	"""docstring for BaseTemplate"""
	def __init__(self, template, **kwargs):
		super(BaseTemplate, self).__init__()
		if issubclass(type(template),Path):
			self.template = str(template)
		else:
			self.template = template
		self.kwargs = kwargs

	def with_language(self,language=None):
		if language is None:
			language = g.language
		self.kwargs['language'] = language
		return self

	def with_dictionnary(self,language=None,dictionnary=None):
		if language is None:
			language = self.kwargs.get('language',g.language)
		if dictionnary is None:
			dictionnary = g.dictionnary
		self.kwargs['language'] = language
		self.kwargs['dictionnary'] = dictionnary
		return self

	def handles_error(self,query_param="error", template_arg="error"):
		self.kwargs[template_arg] = request.args.get(query_param)
		return self

	def handles_success(self,query_param="success", template_arg="success"):
		self.kwargs[template_arg] = request.args.get(query_param)
		return self

	def handles_success_and_error(self,error_query_param="error", error_template_arg="error",success_query_param="success", 
		success_template_arg="success"):
		self.kwargs[error_template_arg] = request.args.get(error_query_param)
		self.kwargs[success_template_arg] = request.args.get(success_query_param)
		return self

	def render(self, **kwargs):
		self.kwargs.update(kwargs)
		return render_template(self.template,**self.kwargs)
		