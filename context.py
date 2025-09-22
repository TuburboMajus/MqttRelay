from temod.ext.holders import clusters, joins, entities
from temod_flask.ext import _readers_holder as _FormReaders
from temod.storage.directory import DirectoryStorage

import random
import os


PARSERS_DB = DirectoryStorage(os.path.join(os.path.dirname(os.path.realpath(__file__)),"db"),createDir=True).subStorage("parsers",createDir=True,mode="")


def init_context(config):
	
	for category, name, entity in entities.tuples():
		_FormReaders.addEntity(entity)
		if name in __builtins__:
			print(f'Warning: cannot register entity {name} in the global context as {name} is already used');continue
		__builtins__[name] = entity

	for category, name, join in joins.tuples():
		_FormReaders.addJoin(join)
		if name in __builtins__:
			print(f'Warning: cannot register join {name} in the global context as {name} is already used');continue
		__builtins__[name] = join

	for category, name, cluster in clusters.tuples():
		_FormReaders.addCluster(cluster)
		if name in __builtins__:
			print(f'Warning: cannot register cluster {name} in the global context as {name} is already used');continue
		__builtins__[name] = cluster


# ** Section ** GenerateSecretKey
def generate_secret_key(length=8):
	alphabet = "abcdefghijklmnopqrstuvwxyz0123456789?!,;:./§$£*µù%+=°)àç_è-('é&²~"
	return "".join([
		getattr(alphabet[random.randint(0,len(alphabet)-1)],["upper","lower"][random.randint(0,1)])()
		for _ in range(length)
	])
# ** EndSection ** GenerateSecretKey