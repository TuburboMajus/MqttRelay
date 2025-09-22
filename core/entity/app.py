# ** Section ** Imports
from temod.base.entity import Entity
from temod.base.attribute import *
from copy import deepcopy

from tools.crypto_envelopes import (
    encrypt_aes_gcm, decrypt_aes_gcm,
    encrypt_chacha20poly1305, decrypt_chacha20poly1305,
    encrypt_aes_cbc_hmac, decrypt_aes_cbc_hmac,
    decrypt_data 
)

import base64
import os
# ** EndSection ** Imports


# ** Section ** Entity_MqttRelay
class MqttRelay(Entity):
	ENTITY_NAME = "mqtt_relay"
	ATTRIBUTES = [
		{"name":"version","type":StringAttribute, "max_length":20, "required":True,"is_id":True,"non_empty":True,"is_nullable":False},
	]
# ** EndSection ** Entity_DigiUpAgri


# ** Section ** Entity_Language
class Language(Entity):
	ENTITY_NAME = "language"
	ATTRIBUTES = [
		{"name":"code","type":StringAttribute,"max_length":10, "required":True,"is_id":True,"is_nullable":False},
		{"name":"name","type":StringAttribute,"max_length":30,"is_nullable":False}
	]
# ** EndSection ** Entity_Language


# ** Section ** Entity_Job
class Job(Entity):
	ENTITY_NAME = "job"
	ATTRIBUTES = [
		{"name":"name","type":StringAttribute, "max_length":50, "required":True,"is_id":True,"is_nullable":False},
		{"name":"state","type":StringAttribute, "max_length":20, "is_nullable":False, "default_value": "IDLE"},
		{"name":"last_state_update","type":DateTimeAttribute, "required":True, "is_nullable":False},
		{"name":"last_exit_code","type":IntegerAttribute}
	]
# ** EndSection ** Entity_Job


# ** Section ** Entity_CryptoConfig
class CryptoConfig(Entity):
	ENTITY_NAME = "crypto_config"
	ATTRIBUTES = [
		{"name":"id","type":IntegerAttribute,"required":True,"is_id":True,"is_nullable":False},
		{"name":"algorithm","type":EnumAttribute,"values":["aes-256-gcm","chacha20-poly1305","aes-256-cbc-hmac"],"required":True,"default_value":"aes-256-gcm","is_nullable":False},
		{"name":"key_source","type":EnumAttribute,"values":["env","kms","db"],"required":True,"default_value":"env","is_nullable":False},
		{"name":"key_id","type":StringAttribute,"max_length":128,"required":True,"default_value":"PRIMARY","is_nullable":False},
		{"name":"iv_bytes","type":IntegerAttribute,"required":True,"default_value":12,"is_nullable":False},
		{"name":"tag_bytes","type":IntegerAttribute,"required":True,"default_value":16,"is_nullable":False},
		{"name":"encoding","type":EnumAttribute,"values":["base64","hex"],"required":True,"default_value":"base64","is_nullable":False},
		{"name":"version","type":IntegerAttribute,"required":True,"default_value":1,"is_nullable":False},
		{"name":"updated_at","type":DateTimeAttribute}
	]


	def encrypt(self, plaintext: bytes | str, key: bytes) -> str:
		"""
		Produce a versioned token that matches the UI expectation:
		  v1.<alg>.<parts...>
		"""
		alg = self['algorithm'].name.lower()
		if alg == "aes-256-gcm":
			inner = encrypt_aes_gcm(plaintext, key, iv_bytes=self['iv_bytes'])
			return f"v1.aes-256-gcm.{inner}"
		elif alg == "chacha20-poly1305":
			inner = encrypt_chacha20poly1305(plaintext, key, nonce_bytes=self['iv_bytes'])
			return f"v1.chacha20-poly1305.{inner}"
		elif alg == "aes-256-cbc-hmac":
			inner = encrypt_aes_cbc_hmac(plaintext, master_key=key, key_id=self['key_id'], iv_bytes=max(self['iv_bytes'], 16))
			return f"v1.aes-256-cbc-hmac.{inner}"
		else:
			raise ValueError(f"Unknown algorithm: {self['algorithm']}")
# ** EndSection ** Entity_CryptoConfig


# ** Section ** Entity_CryptoKey
class CryptoKey(Entity):
	ENTITY_NAME = "crypto_key"
	ATTRIBUTES = [
		{"name":"key_id","type":StringAttribute,"max_length":128,"required":True,"is_id":True,"is_nullable":False},
		{"name":"key_b64","type":StringAttribute,"max_length":64,"required":True,"is_nullable":False},
		{"name":"version","type":IntegerAttribute,"required":True,"default_value":1,"is_nullable":False},
		{"name":"updated_at","type":DateTimeAttribute}
	]

	# ---- key retrieval ----
	def _parse_key_material(raw: str) -> bytes:
		"""
		Accepts base64 or hex; raises ValueError if not 32 bytes after decoding.
		"""
		raw = (raw or "").strip()
		# try base64
		try:
			k = base64.b64decode(raw, validate=True)
			if len(k) == 32:
				return k
		except Exception:
			pass

		# try hex
		try:
			k = bytes.fromhex(raw)
			if len(k) == 32:
				return k
		except Exception:
			pass
		raise ValueError("Key material must be 32 bytes (base64 or hex).")

	def _load_key_from_env(key_id: str) -> bytes:
		# Environment variable name convention:
		#   MQTTRELAY_ENC_KEY_<KEY_ID>, e.g. MQTTRELAY_ENC_KEY_PRIMARY
		env_name = f"MQTT_RELAY_ENC_KEY_{key_id.upper()}"
		raw = os.environ.get(env_name)
		if not raw:
			raise RuntimeError(f"Missing environment variable {env_name}")
		return CryptoKey._parse_key_material(raw)

	def _load_key_from_db(key_id: str) -> bytes:
		"""
		If you choose to store keys in DB (discouraged), implement a model
		that returns encrypted or wrapped key material, unwrap it here.
		For demo, we read a table 'crypto_keys' with columns (key_id, key_b64).
		"""
		keys = list(CryptoKey.storage.list(key_id=key_id, orderby="version DESC", limit=1))
		if len(keys) == 0:
			raise RuntimeError(f"Key not found in DB for key_id={key_id}")
		return CryptoKey._parse_key_material(keys[0]["key_b64"])

	def _load_key_from_kms(key_id: str) -> bytes:
		"""
		Integrate your KMS/HSM here.
		E.g., call your KMS to fetch/export a 32-byte DEK by alias key_id.
		"""
		raise NotImplementedError("KMS key retrieval not implemented")

	def get_key_bytes(key_source: str, key_id: str) -> bytes:
		if key_source.name == "env":
			return CryptoKey._load_key_from_env(key_id)
		elif key_source.name == "db":
			return CryptoKey._load_key_from_db(key_id)
		elif key_source.name == "kms":
			return CryptoKey._load_key_from_kms(key_id)
		else:
			raise RuntimeError(f"Unsupported key_source: {key_source}")
# ** EndSection ** Entity_CryptoKey