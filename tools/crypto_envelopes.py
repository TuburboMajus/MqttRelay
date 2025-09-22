# crypto_envelopes.py
from __future__ import annotations
import base64, os, hashlib
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes, hmac
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


# ----------------------------- helpers -----------------------------

class EncryptionError(Exception):
    pass

def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")

def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))

def _ensure_key_len(key: bytes, expected: int = 32) -> None:
    if not isinstance(key, (bytes, bytearray)) or len(key) != expected:
        raise ValueError(f"key must be {expected} bytes")

def _hkdf(master_key: bytes, length: int, info: bytes, key_id: str = "PRIMARY") -> bytes:
    """
    Derive subkeys from master_key. Salt is derived from key_id so different
    key aliases produce different subkeys even with the same master_key.
    """
    salt = hashlib.sha256(key_id.encode("utf-8")).digest()
    hkdf = HKDF(
        algorithm=hashes.SHA256(), length=length, salt=salt, info=info
    )
    return hkdf.derive(master_key)

# ----------------------- AES-256-GCM (AEAD) ------------------------

def encrypt_aes_gcm(plaintext: bytes | str, key: bytes, *, iv_bytes: int = 12, aad: Optional[bytes] = None) -> str:
    """
    Returns token: base64(iv) + '.' + base64(ciphertext_and_tag)
    """
    _ensure_key_len(key, 32)
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    iv = os.urandom(iv_bytes)  # 12 recommended
    aead = AESGCM(key)
    ct = aead.encrypt(iv, plaintext, aad)  # returns ct||tag
    return f"{_b64e(iv)}.{_b64e(ct)}"

def decrypt_aes_gcm(token: str, key: bytes, *, aad: Optional[bytes] = None) -> bytes:
    _ensure_key_len(key, 32)
    try:
        iv_b64, ct_b64 = token.split(".", 1)
        iv, ct = _b64d(iv_b64), _b64d(ct_b64)
        aead = AESGCM(key)
        return aead.decrypt(iv, ct, aad)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise EncryptionError(f"AES-GCM decrypt failed: {e!s}") from e


# ------------------- ChaCha20-Poly1305 (AEAD) ---------------------

def encrypt_chacha20poly1305(plaintext: bytes | str, key: bytes, *, nonce_bytes: int = 12, aad: Optional[bytes] = None) -> str:
    """
    Returns token: base64(nonce) + '.' + base64(ciphertext_and_tag)
    """
    _ensure_key_len(key, 32)
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    nonce = os.urandom(nonce_bytes)  # 12 recommended
    aead = ChaCha20Poly1305(key)
    ct = aead.encrypt(nonce, plaintext, aad)  # returns ct||tag
    return f"{_b64e(nonce)}.{_b64e(ct)}"

def decrypt_chacha20poly1305(token: str, key: bytes, *, aad: Optional[bytes] = None) -> bytes:
    _ensure_key_len(key, 32)
    try:
        n_b64, ct_b64 = token.split(".", 1)
        nonce, ct = _b64d(n_b64), _b64d(ct_b64)
        aead = ChaCha20Poly1305(key)
        return aead.decrypt(nonce, ct, aad)
    except Exception as e:
        raise EncryptionError(f"ChaCha20-Poly1305 decrypt failed: {e!s}") from e


# -------------- AES-256-CBC + HMAC-SHA256 (EtM) -------------------

def encrypt_aes_cbc_hmac(plaintext: bytes | str, master_key: bytes, *, key_id: str = "PRIMARY", iv_bytes: int = 16) -> str:
    """
    Encrypt-then-MAC with independent keys derived via HKDF from master_key.
    Token format: base64(iv) + '.' + base64(ciphertext) + '.' + base64(tag)
    """
    _ensure_key_len(master_key, 32)
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")

    # Derive separate keys to avoid key reuse across ENC/MAC
    enc_key = _hkdf(master_key, 32, b"aes-cbc|enc", key_id=key_id)
    mac_key = _hkdf(master_key, 32, b"aes-cbc|mac", key_id=key_id)

    iv = os.urandom(iv_bytes)  # 16 bytes for AES-CBC
    # PKCS7 pad to AES block (128 bits)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()

    cipher = Cipher(algorithms.AES(enc_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ct = encryptor.update(padded) + encryptor.finalize()

    # HMAC over version|alg|iv|ct (versioned domain separation)
    h = hmac.HMAC(mac_key, hashes.SHA256())
    h.update(b"v1|aes-256-cbc-hmac|")
    h.update(iv)
    h.update(ct)
    tag = h.finalize()

    return f"{_b64e(iv)}.{_b64e(ct)}.{_b64e(tag)}"

def decrypt_aes_cbc_hmac(token: str, master_key: bytes, *, key_id: str = "PRIMARY") -> bytes:
    _ensure_key_len(master_key, 32)
    try:
        iv_b64, ct_b64, tag_b64 = token.split(".", 2)
        iv, ct, tag = _b64d(iv_b64), _b64d(ct_b64), _b64d(tag_b64)

        enc_key = _hkdf(master_key, 32, b"aes-cbc|enc", key_id=key_id)
        mac_key = _hkdf(master_key, 32, b"aes-cbc|mac", key_id=key_id)

        # Verify HMAC before decrypting
        h = hmac.HMAC(mac_key, hashes.SHA256())
        h.update(b"v1|aes-256-cbc-hmac|")
        h.update(iv)
        h.update(ct)
        h.verify(tag)  # raises InvalidSignature on mismatch

        cipher = Cipher(algorithms.AES(enc_key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ct) + decryptor.finalize()

        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()
        return plaintext
    except Exception as e:
        raise EncryptionError(f"AES-CBC-HMAC decrypt failed: {e!s}") from e


# --------------------------- convenience --------------------------

def encrypt_data(plaintext: bytes | str, key: bytes, *, algorithm: str = "aes-256-gcm", key_id: str = "PRIMARY") -> str:
    """
    Unified encryptor that dispatches to the selected algorithm.

    Returns a compact token string safe for DB storage.
    """
    alg = algorithm.lower()
    if alg in ("aes-256-gcm", "aesgcm", "gcm"):
        return "v1.aes-256-gcm." + encrypt_aes_gcm(plaintext, key)
    elif alg in ("chacha20-poly1305", "chacha20poly1305", "chacha"):
        return "v1.chacha20-poly1305." + encrypt_chacha20poly1305(plaintext, key)
    elif alg in ("aes-256-cbc-hmac", "aes-cbc-hmac", "cbc-hmac"):
        return "v1.aes-256-cbc-hmac." + encrypt_aes_cbc_hmac(plaintext, key, key_id=key_id)
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")


def decrypt_data(token: str, key: bytes, *, key_id: str = "PRIMARY") -> bytes:
    """
    Unified decryptor. Accepts tokens produced by encrypt_data.
    """
    try:
        prefix, alg, rest = token.split(".", 2)
    except ValueError:
        raise EncryptionError("Invalid token format")

    if prefix != "v1":
        raise EncryptionError(f"Unsupported token version: {prefix}")

    alg = alg.lower()
    if alg == "aes-256-gcm":
        return decrypt_aes_gcm(rest, key)
    elif alg == "chacha20-poly1305":
        return decrypt_chacha20poly1305(rest, key)
    elif alg == "aes-256-cbc-hmac":
        return decrypt_aes_cbc_hmac(rest, key, key_id=key_id)
    else:
        raise EncryptionError(f"Unsupported algorithm in token: {alg}")