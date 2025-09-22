from flask import current_app, render_template, request, redirect, url_for, abort, session, g, jsonify
from flask_login import LoginManager, login_required, current_user

from temod_flask.utils.content_readers import body_content
from temod_flask.blueprint import MultiLanguageBlueprint
from temod_flask.blueprint.utils import Paginator

from temod.base.condition import Not, Equals
from temod.base.attribute import *

from front.renderers.users import AuthenticatedUserTemplate
from typing import Optional, Iterable, Tuple

from tools.crypto_envelopes import (
	encrypt_aes_gcm, decrypt_aes_gcm,
	encrypt_chacha20poly1305, decrypt_chacha20poly1305,
	encrypt_aes_cbc_hmac, decrypt_aes_cbc_hmac,
	decrypt_data 
)

from datetime import datetime, date
from pathlib import Path

import traceback
import base64
import json
import os


ALLOWED_ALGOS = {"aes-256-gcm", "chacha20-poly1305", "aes-256-cbc-hmac"}
ALLOWED_SOURCES = {"env", "kms", "db"}
ALLOWED_ENCODINGS = {"base64", "hex"}

def _ok(msg: str = "ok", **extra):
	return jsonify({"message": msg, **extra})

def _bad(msg: str, code: int = 400):
	return jsonify({"message": msg}), code


def _decrypt_token(token: str, key_for_id) -> bytes:
	"""
	token format: v<version>.<algorithm>.<...>
	key_for_id: callable(key_id:str) -> bytes (needed for CBC+HMAC cases if you store key_id separately)
	For GCM/ChaCha tokens we only need the 'key_for_id(active)' (the token doesn't embed key_id),
	so pass a lambda using the active key_id where appropriate.
	"""
	# We can reuse decrypt_data if the token matches v1.<alg>...
	return decrypt_data(token, key_for_id("ACTIVE"), key_id="ACTIVE")



general_blueprint = MultiLanguageBlueprint('general',__name__, load_in_g=True, default_config={
	"templates_folder":"{language}/general",
	"general_per_page":100,
}, dictionnary_selector=lambda lg:lg['code'])



@general_blueprint.route('/settings', methods=['GET'])
@login_required
@general_blueprint.with_dictionnary
def settings():
	return AuthenticatedUserTemplate(
	Path(general_blueprint.configuration["templates_folder"].format(language=g.language['code'])).joinpath("settings.html"),
	user=current_user['user'], metrics=list(Metric.storage.list())
).handles_success_and_error().with_dictionnary().with_sidebar("settings").render()


@general_blueprint.route('/crypto', methods=['GET'])
@login_required
@general_blueprint.with_dictionnary
def getCrypto():
	return CryptoConfig.storage.get().to_dict()


@general_blueprint.route('/crypto/update', methods=['PUT'])
@login_required
@general_blueprint.with_dictionnary
@body_content('json')
def updateCrypto(form):

	crypto_config = CryptoConfig.storage.get()
	objects_with_credentials = [ClientDestination]
	for object_with_credentials in objects_with_credentials:
		c = object_with_credentials.storage.count(
			Not(Equals(StringAttribute("encryption_version",value=f"{crypto_config['key_id']}.{crypto_config['version']}"))),
			Not(Equals(StringAttribute("encryption_version")))
		)
		if c > 0:
			return _bad(f"Cannot update crypto config some passwords are still encrypted with old version. Re-enncrypt passwords before updating the crypto config",400)

	crypto_config = crypto_config.takeSnapshot()
	crypto_config.setAttributes(**form)

	CryptoConfig.storage.updateOnSnapshot(crypto_config)
	return crypto_config.to_dict()


@general_blueprint.route('/crypto/test', methods=['POST'])
@login_required
@general_blueprint.with_dictionnary
@body_content('json')
def testCrypto(form):

	crypto_config = CryptoConfig.storage.get()
	plaintext = form.get("plaintext", "")

	try:
		key = CryptoKey.get_key_bytes(crypto_config['key_source'], crypto_config['key_id'])
	except Exception as e:
		traceback.print_exc()
		return _bad(f"Key load failed: {e}", 400)

	try:
		token = crypto_config.encrypt(plaintext, key)
		out = decrypt_data(token, key, key_id=crypto_config['key_id'])
		return jsonify({
			"ciphertext": token,
			"decrypted": out.decode("utf-8", "replace")
		})
	except Exception as e:
		traceback.print_exc()
		return _bad(f"Test failed: {e}", 400)


@general_blueprint.route('/crypto/rotate_key', methods=['POST'])
@login_required
@general_blueprint.with_dictionnary
@body_content('json')
def rotateCryptoKey(form):
	"""
	Rotate the active key. Behavior by key_source:
	- env: we cannot set env vars here; instruct operator to update MQTT_RELAY_ENC_KEY_<KEY_ID>
	- kms: call your KMS rotation or create a new key version (implement _load_key_from_kms/_rotate_kms_key)
	- db: generate a new 32-byte key and store it (table crypto_keys)
	"""
	cfg = CryptoConfig.storage.get().takeSnapshot()
	key_id = (form.get("key_id") or cfg['key_id']).strip() or cfg['key_id']

	msg = ""
	if cfg['key_source'].name == "env":
		# Bump version for bookkeeping; operator must update env var out-of-band.
		old_key = CryptoKey.get_key_bytes(cfg['key_source'].name, key_id)
		CryptoKey.storage.create(CryptoKey(
			key_id=key_id, version=cfg['version'], key_b64=old_key.decode("ascii"), updated_at=datetime.now()
		))
		cfg['version'] += 1
		cfg['updated_at'] = datetime.now()
		msg = (f"Version bumped to v{cfg['version']}. Update MQTT_RELAY_ENC_KEY_{key_id.upper()} in your environment, then re-encrypt.")

	elif cfg['key_source'].name == "db":
		new_key = os.urandom(32)
		CryptoKey.storage.create(CryptoKey(
			key_id=key_id, version=cfg['version']+1, key_b64=base64.b64encode(new_key).decode("ascii"),updated_at=datetime.now()
		))
		cfg['version'] += 1
		cfg['updated_at'] = datetime.now()
		msg = f"DB key for {key_id} replaced; config version is now v{cfg['version']}."

	elif cfg['key_source'].name == "kms":
		# Implement your KMS rotation here
		return _bad("KMS rotation not implemented in this version.", 501)

	else:
		return _bad(f"Unsupported key_source: {cfg['key_source']}", 400)

	CryptoConfig.storage.updateOnSnapshot(cfg)

	return jsonify({"message": msg, "config": cfg.to_dict()})


@general_blueprint.route('/crypto', methods=['POST'])
@login_required
@general_blueprint.with_dictionnary
def reCrypto():
	"""
	Re-encrypt all stored passwords in ServiceCredential that are not using
	the active (algorithm, key_id). Assumes each row stores the key_id used.
	"""
	cfg = CryptoConfig.storage.get().takeSnapshot()

	# load active key once
	try:
		active_key = CryptoKey.get_key_bytes(cfg['key_source'], cfg['key_id'])
	except Exception as e:
		traceback.print_exc()
		return _bad(f"Key load failed: {e}", 400)

	updated = 0
	failed  = 0

	objects_with_credentials = [ClientDestination]

	for object_with_credentials in objects_with_credentials:
		for obj in object_with_credentials.storage.list(Not(Equals(StringAttribute("encryption_version",value=f"{cfg['key_id']}.{cfg['version']}"))),Not(Equals(StringAttribute("encryption_version")))):
			try:
				# old key source & id assumed same as current cfg.key_source but row.key_id may differ.
				# If you mix sources per-row, add a column and branch key retrieval here.
				obj.takeSnapshot()

				old_key_id = CryptoKey.storage.get(version=int(obj['encryption_version'].split('.')[1]),key_id=obj['encryption_version'].split('.')[0])['key_id']
				old_key = CryptoKey.get_key_bytes(cfg['key_source'], old_key_id)
				print(old_key_id, old_key, obj['password_enc'].decode('ascii'))

				# Decrypt using old key id (our tokens include alg but not key id)
				plaintext = decrypt_data(obj['password_enc'].decode('ascii'), old_key, key_id=old_key_id)

				# Encrypt with active cfg & active_key
				new_token = cfg.encrypt(plaintext, active_key)

				obj['password_enc'] = new_token.encode('ascii')
				obj['encryption_version'] = f"{cfg['key_id']}.{cfg['version']}"
				updated += 1

				object_with_credentials.storage.updateOnSnapshot(obj)

			except Exception:
				traceback.print_exc()
				failed += 1
				# (Optional) collect IDs to report

	return jsonify({"message": "Re-encryption complete", "updated_count": updated, "failed_count": failed})
