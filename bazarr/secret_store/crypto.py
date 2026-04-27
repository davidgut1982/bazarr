# coding=utf-8
"""Symmetric crypto primitives for secrets at rest.

Wraps `itsdangerous.URLSafeSerializer` (the same primitive `plex/security.py`
uses) but adds:

1. A versioned marker prefix (`enc:v1:`) on the stored ciphertext. The
   prefix lets the read path tell "this value is already encrypted, decrypt
   it" apart from "this value is still plaintext, the auto-migrator hasn't
   touched it yet" without a separate boolean flag per field.

2. A salt + timestamp inside the signed payload so two encryptions of the
   same plaintext produce different ciphertext (defends against equality
   inference if config.yaml leaks).

3. A single master key (`general.secrets_encryption_key`) instead of a
   per-namespace key like `plex.encryption_key`. One key to rotate, one
   key to redact.

The marker is intentionally NOT cryptographic. An attacker who can write
config.yaml can drop a value in plaintext without the marker; the read
path will treat it as plaintext and either decrypt-fail (signed payload
loaded as raw text) or hand it back as-is. We are protecting against
accidental disclosure (logs, screenshots, support bundles), not a local
attacker who already owns the host.
"""

import logging
import secrets as _secrets
import time

from itsdangerous import BadPayload, BadSignature, URLSafeSerializer

logger = logging.getLogger(__name__)

# Versioned marker. Bumping the suffix lets a future change rotate the
# format (e.g. AEAD-based payload) and still detect legacy ciphertext.
SECRET_MARKER_PREFIX = "enc:v1:"

# Generated key length in bytes (token_urlsafe doubles to ~43 chars).
_MASTER_KEY_BYTES = 32


def _generate_master_key() -> str:
    return _secrets.token_urlsafe(_MASTER_KEY_BYTES)


def get_master_key(settings_obj=None) -> str:
    """Return the master encryption key, creating one if missing.

    Reads/writes `settings.general.secrets_encryption_key`. The key is
    generated on first call when the value is absent or empty - mirrors
    the `flask_secret_key` lifecycle, no extra config step for the user.

    `settings_obj` is the dynaconf settings root; defaults to
    `app.config.settings`. Injectable for tests so we don't need a real
    bazarr config to be loaded.
    """
    if settings_obj is None:
        from app.config import settings as settings_obj  # noqa: PLC0415

    general = settings_obj.general
    key = getattr(general, "secrets_encryption_key", None)
    if not key or (isinstance(key, str) and not key.strip()):
        key = _generate_master_key()
        general.secrets_encryption_key = key
        logger.info("Generated new master secrets_encryption_key on first boot")
    return key


def is_encrypted(value) -> bool:
    """True iff `value` is a string carrying the SECRET_MARKER_PREFIX.

    Used by the read path to decide "decrypt this" vs "leave alone /
    auto-migrate". Non-string and empty values are NOT encrypted (an
    empty credential is just an empty credential, no migration needed).
    """
    return isinstance(value, str) and value.startswith(SECRET_MARKER_PREFIX)


def encrypt_secret(plaintext: str, master_key: str = None) -> str:
    """Encrypt `plaintext` and return a marker-prefixed ciphertext.

    Empty / falsy plaintext is returned unchanged - we don't waste bytes
    encrypting an empty string, and the read path treats empty as
    "credential not configured" anyway.
    """
    if not plaintext:
        return plaintext
    if not isinstance(plaintext, str):
        raise TypeError(f"encrypt_secret expects str, got {type(plaintext).__name__}")
    if is_encrypted(plaintext):
        # Caller passed an already-encrypted value through. Return as-is
        # so callers can be idempotent (re-encrypting on every save would
        # rotate ciphertext on every write for no reason).
        return plaintext

    if master_key is None:
        master_key = get_master_key()

    serializer = URLSafeSerializer(master_key)
    payload = {
        "v": 1,
        "secret": plaintext,
        "salt": _secrets.token_hex(16),
        "ts": int(time.time()),
    }
    return SECRET_MARKER_PREFIX + serializer.dumps(payload)


def decrypt_secret(value, master_key: str = None) -> str:
    """Decrypt `value` if it carries the marker, else return it as-is.

    Tolerant by design: the read path may encounter a freshly-installed
    value (plaintext, no marker) or an encrypted one. Both must work, so
    a value without the marker is returned unchanged. The auto-migrator
    in commit 2 is responsible for rewriting plaintext to ciphertext.

    Raises `ValueError` only on tampered / mis-keyed ciphertext (marker
    present, but URLSafeSerializer rejects the payload). Callers that
    boot with the wrong master key will see this and can surface a clear
    error instead of silently serving garbage.
    """
    if not isinstance(value, str) or not value:
        return value
    if not is_encrypted(value):
        return value

    if master_key is None:
        master_key = get_master_key()

    payload_text = value[len(SECRET_MARKER_PREFIX):]
    serializer = URLSafeSerializer(master_key)
    try:
        payload = serializer.loads(payload_text)
    except (BadSignature, BadPayload, ValueError) as e:
        raise ValueError(
            "Failed to decrypt secret: ciphertext was tampered with or the "
            "master key has changed. Inspect general.secrets_encryption_key "
            "in config.yaml."
        ) from e

    if not isinstance(payload, dict) or "secret" not in payload:
        raise ValueError("Decrypted payload has unexpected shape")
    return payload["secret"]
