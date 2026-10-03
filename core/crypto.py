# Crypto helpers for CryptoConfig/CryptoKey (SQLAlchemy port of core/entity/app.py)
import base64
import os

from tools.crypto_envelopes import (
    encrypt_aes_gcm, encrypt_chacha20poly1305, encrypt_aes_cbc_hmac,
)
from core.repository import repos


def crypto_config_encrypt(cfg, plaintext, key: bytes) -> str:
    """Produce a versioned token: v1.<alg>.<parts...> using the given CryptoConfig row."""
    alg = cfg.algorithm.lower()
    if alg == "aes-256-gcm":
        inner = encrypt_aes_gcm(plaintext, key, iv_bytes=cfg.iv_bytes)
        return f"v1.aes-256-gcm.{inner}"
    elif alg == "chacha20-poly1305":
        inner = encrypt_chacha20poly1305(plaintext, key, nonce_bytes=cfg.iv_bytes)
        return f"v1.chacha20-poly1305.{inner}"
    elif alg == "aes-256-cbc-hmac":
        inner = encrypt_aes_cbc_hmac(plaintext, master_key=key, key_id=cfg.key_id, iv_bytes=max(cfg.iv_bytes, 16))
        return f"v1.aes-256-cbc-hmac.{inner}"
    raise ValueError(f"Unknown algorithm: {cfg.algorithm}")


def _parse_key_material(raw: str) -> bytes:
    """Accepts base64 or hex; raises ValueError if not 32 bytes after decoding."""
    raw = (raw or "").strip()
    try:
        k = base64.b64decode(raw, validate=True)
        if len(k) == 32:
            return k
    except Exception:
        pass
    try:
        k = bytes.fromhex(raw)
        if len(k) == 32:
            return k
    except Exception:
        pass
    raise ValueError("Key material must be 32 bytes (base64 or hex).")


def _load_key_from_env(key_id: str) -> bytes:
    env_name = f"MQTT_RELAY_ENC_KEY_{key_id.upper()}"
    raw = os.environ.get(env_name)
    if not raw:
        raise RuntimeError(f"Missing environment variable {env_name}")
    return _parse_key_material(raw)


def _load_key_from_db(key_id: str) -> bytes:
    keys = repos['CryptoKey'].list(key_id=key_id, orderby="version DESC", limit=1)
    if not keys:
        raise RuntimeError(f"Key not found in DB for key_id={key_id}")
    return _parse_key_material(keys[0].key_b64)


def _load_key_from_kms(key_id: str) -> bytes:
    raise NotImplementedError("KMS key retrieval not implemented")


def get_key_bytes(key_source: str, key_id: str) -> bytes:
    if key_source == "env":
        return _load_key_from_env(key_id)
    elif key_source == "db":
        return _load_key_from_db(key_id)
    elif key_source == "kms":
        return _load_key_from_kms(key_id)
    raise RuntimeError(f"Unsupported key_source: {key_source}")
