from flask import current_app, render_template, request, redirect, url_for, abort, session, g, jsonify, Blueprint
from flask_login import login_required, current_user

from core.repository import repos
from core.models import CryptoConfig, CryptoKey, ClientDestination, Metric
from core.crypto import crypto_config_encrypt, get_key_bytes

from tools.crypto_envelopes import (
    encrypt_aes_gcm, decrypt_aes_gcm,
    encrypt_chacha20poly1305, decrypt_chacha20poly1305,
    encrypt_aes_cbc_hmac, decrypt_aes_cbc_hmac,
    decrypt_data
)

from typing import Optional, Iterable, Tuple
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


bp = Blueprint('general', __name__)

def setup(config=None):
    """Setup blueprint with configuration."""
    return bp



@bp.route('/settings', methods=['GET'])
@login_required
def settings():
    current_app.logger.debug("Route [general.settings] rendering settings page")
    metrics = repos['Metric'].list()
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/general/settings.html",
        user=current_user,
        metrics=metrics
    )


@bp.route('/crypto', methods=['GET'])
@login_required
def getCrypto():
    current_app.logger.debug("Route [general.getCrypto] fetching crypto config")
    cc = repos['CryptoConfig'].list()
    if cc:
        return jsonify(cc[0].to_dict())
    return jsonify({})


@bp.route('/crypto/update', methods=['PUT'])
@login_required
def updateCrypto():
    current_app.logger.debug("Route [general.updateCrypto] updating crypto config")
    
    data = request.form.to_dict() if request.form else request.get_json()
    
    crypto_configs = repos['CryptoConfig'].list()
    if not crypto_configs:
        current_app.logger.error("Route [general.updateCrypto] no crypto config found")
        return _bad("No crypto config found", 404)
    
    crypto_config = crypto_configs[0]
    
    # Check if any ClientDestinations are using old encryption version
    old_version_key = f"{crypto_config.key_id}.{crypto_config.version}"
    stale_count = 0
    for dest in repos['ClientDestination'].list():
        if dest.encryption_version and dest.encryption_version != old_version_key:
            stale_count += 1
    
    if stale_count > 0:
        current_app.logger.warning("Route [general.updateCrypto] stale-encrypted passwords found (%s)", stale_count)
        return _bad(f"Cannot update crypto config; {stale_count} passwords still encrypted with old version. Re-encrypt passwords first.", 400)
    
    try:
        updates = {k: v for k, v in data.items() if k in ['key_id', 'version', 'algorithm', 'key_source']}
        repos['CryptoConfig'].update(crypto_config, **updates)
        current_app.logger.info("Route [general.updateCrypto] crypto config updated (key_id=%s, version=%s)", crypto_config.key_id, crypto_config.version)
        return jsonify(crypto_config.to_dict())
    except Exception as e:
        current_app.logger.exception("Route [general.updateCrypto] error: %s", e)
        return _bad(str(e), 500)


@bp.route('/crypto/test', methods=['POST'])
@login_required
def testCrypto():
    current_app.logger.debug("Route [general.testCrypto] testing crypto config")
    
    data = request.form.to_dict() if request.form else request.get_json()
    plaintext = data.get("plaintext", "")
    
    crypto_configs = repos['CryptoConfig'].list()
    if not crypto_configs:
        return _bad("No crypto config found", 404)
    
    crypto_config = crypto_configs[0]
    
    try:
        key = get_key_bytes(crypto_config.key_source, crypto_config.key_id)
    except Exception as e:
        traceback.print_exc()
        current_app.logger.exception("Route [general.testCrypto] key load failed: %s", e)
        return _bad(f"Key load failed: {e}", 400)
    
    try:
        token = crypto_config_encrypt(crypto_config, plaintext, key)
        out = decrypt_data(token, key, key_id=crypto_config.key_id)
        current_app.logger.info("Route [general.testCrypto] crypto test succeeded")
        return jsonify({
            "ciphertext": token,
            "decrypted": out.decode("utf-8", "replace")
        })
    except Exception as e:
        traceback.print_exc()
        current_app.logger.exception("Route [general.testCrypto] crypto test failed: %s", e)
        return _bad(f"Test failed: {e}", 400)


@bp.route('/crypto/rotate_key', methods=['POST'])
@login_required
def rotateCryptoKey():
    """
    Rotate the active key. Behavior by key_source:
    - env: we cannot set env vars here; instruct operator to update MQTT_RELAY_ENC_KEY_<KEY_ID>
    - kms: call your KMS rotation or create a new key version
    - db: generate a new 32-byte key and store it
    """
    current_app.logger.debug("Route [general.rotateCryptoKey] rotating crypto key")
    
    data = request.form.to_dict() if request.form else request.get_json()
    
    crypto_configs = repos['CryptoConfig'].list()
    if not crypto_configs:
        return _bad("No crypto config found", 404)
    
    cfg = crypto_configs[0]
    key_id = (data.get("key_id") or cfg.key_id).strip() or cfg.key_id
    
    current_app.logger.debug("Route [general.rotateCryptoKey] rotating key (key_id=%s)", key_id)
    
    msg = ""
    if cfg.key_source == "env":
        # Bump version for bookkeeping
        old_key = get_key_bytes(cfg.key_source, key_id)
        repos['CryptoKey'].create(CryptoKey(
            key_id=key_id, version=cfg.version, key_b64=old_key.decode("ascii"), updated_at=datetime.utcnow()
        ))
        repos['CryptoConfig'].update(cfg, version=cfg.version + 1, updated_at=datetime.utcnow())
        msg = f"Version bumped to v{cfg.version + 1}. Update MQTT_RELAY_ENC_KEY_{key_id.upper()} in your environment, then re-encrypt."
    
    elif cfg.key_source == "db":
        new_key = os.urandom(32)
        repos['CryptoKey'].create(CryptoKey(
            key_id=key_id, version=cfg.version + 1, key_b64=base64.b64encode(new_key).decode("ascii"), updated_at=datetime.utcnow()
        ))
        repos['CryptoConfig'].update(cfg, version=cfg.version + 1, updated_at=datetime.utcnow())
        msg = f"DB key for {key_id} replaced; config version is now v{cfg.version + 1}."
    
    elif cfg.key_source == "kms":
        current_app.logger.warning("Route [general.rotateCryptoKey] KMS rotation not implemented")
        return _bad("KMS rotation not implemented in this version.", 501)
    
    else:
        current_app.logger.warning("Route [general.rotateCryptoKey] unsupported key_source=%s", cfg.key_source)
        return _bad(f"Unsupported key_source: {cfg.key_source}", 400)
    
    current_app.logger.info("Route [general.rotateCryptoKey] key rotated (key_id=%s, version=%s)", key_id, cfg.version)
    return jsonify({"message": msg, "config": cfg.to_dict()})


@bp.route('/crypto', methods=['POST'])
@login_required
def reCrypto():
    """
    Re-encrypt all stored passwords in ClientDestination that are not using
    the active (algorithm, key_id).
    """
    current_app.logger.debug("Route [general.reCrypto] re-encrypting stored passwords")
    
    crypto_configs = repos['CryptoConfig'].list()
    if not crypto_configs:
        return _bad("No crypto config found", 404)
    
    cfg = crypto_configs[0]
    
    # load active key once
    try:
        active_key = get_key_bytes(cfg.key_source, cfg.key_id)
    except Exception as e:
        traceback.print_exc()
        current_app.logger.exception("Route [general.reCrypto] key load failed: %s", e)
        return _bad(f"Key load failed: {e}", 400)
    
    updated = 0
    failed = 0
    
    try:
        for dest in repos['ClientDestination'].list():
            try:
                old_version_key = f"{cfg.key_id}.{cfg.version}"
                
                if dest.encryption_version and dest.encryption_version != old_version_key:
                    # Decrypt using old key
                    old_parts = dest.encryption_version.split('.')
                    old_key_id = old_parts[0] if len(old_parts) > 0 else cfg.key_id
                    old_key = get_key_bytes(cfg.key_source, old_key_id)
                    
                    # Decrypt password
                    plaintext = decrypt_data(dest.password_enc.decode('ascii') if isinstance(dest.password_enc, bytes) else dest.password_enc, old_key, key_id=old_key_id)
                    
                    # Encrypt with active cfg & active_key
                    new_token = crypto_config_encrypt(cfg, plaintext, active_key)
                    
                    # Update destination
                    repos['ClientDestination'].update(
                        dest,
                        password_enc=new_token.encode('ascii') if isinstance(new_token, str) else new_token,
                        encryption_version=old_version_key
                    )
                    updated += 1
            except Exception:
                traceback.print_exc()
                current_app.logger.exception("Route [general.reCrypto] re-encryption failed for destination id=%s", dest.id)
                failed += 1
    except Exception as e:
        current_app.logger.exception("Route [general.reCrypto] error: %s", e)
        return _bad(str(e), 500)
    
    current_app.logger.info("Route [general.reCrypto] re-encryption complete (updated=%s, failed=%s)", updated, failed)
    return jsonify({"message": "Re-encryption complete", "updated_count": updated, "failed_count": failed})
