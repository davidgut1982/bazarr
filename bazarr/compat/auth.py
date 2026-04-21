from __future__ import annotations
import base64
import hashlib
import hmac
import json
import time
from typing import Tuple

import jwt as pyjwt

from bazarr.app.config import settings


class CompatBootError(RuntimeError):
    """Raised when compat secrets fail the boot-time self-test."""


def validate_compat_token(supplied: str | None) -> bool:
    """Constant-time compare against settings.compat_endpoint.token. Never `==`."""
    if not supplied:
        return False
    expected = settings.compat_endpoint.token or ""
    if not expected:
        return False
    return hmac.compare_digest(str(supplied), str(expected))


def _get_jwt_secret() -> str:
    return settings.compat_endpoint.jwt_secret or ""


def mint_jwt(claims_extra: dict | None = None) -> str:
    secret = _get_jwt_secret()
    if len(secret) < 32:
        raise CompatBootError("jwt_secret missing or too short")
    now = int(time.time())
    claims = {
        "iat": now,
        "exp": now + int(settings.compat_endpoint.jwt_ttl_seconds),
    }
    if claims_extra:
        claims.update(claims_extra)
    return pyjwt.encode(claims, secret, algorithm="HS256")


def validate_jwt(token: str | None) -> Tuple[bool, dict]:
    if not token:
        return False, {}
    secret = _get_jwt_secret()
    if len(secret) < 32:
        return False, {}
    try:
        claims = pyjwt.decode(token, secret, algorithms=["HS256"])
        return True, claims
    except pyjwt.PyJWTError:
        return False, {}


def boot_hmac_selftest() -> None:
    """Assert all three secrets exist, are >=32 chars, and can produce HMAC output.

    Called during blueprint registration when enabled=True. Aborts fail-closed.
    """
    for name in ("token", "jwt_secret", "file_id_secret"):
        val = getattr(settings.compat_endpoint, name, "") or ""
        if len(val) < 32:
            raise CompatBootError(f"compat_endpoint.{name} missing or <32 chars")
    # Known-plaintext HMAC: must produce non-empty bytes.
    for secret_name in ("jwt_secret", "file_id_secret"):
        secret = getattr(settings.compat_endpoint, secret_name).encode()
        tag = hmac.new(secret, b"selftest", hashlib.sha256).hexdigest()
        if not tag or len(tag) != 64:
            raise CompatBootError(f"HMAC self-test failed for {secret_name}")


def _hmac_sign(secret: bytes, payload_bytes: bytes) -> bytes:
    return hmac.new(secret, payload_bytes, hashlib.sha256).digest()


def mint_file_id(provider: str, native_id: str, language: str, release_info: str) -> str:
    """Produce a stateless HMAC-signed file_id.

    Payload shape (sort_keys, compact separators):
        {"p": provider, "i": native_id, "l": language,
         "r": sha1(release_info)[:10], "exp": <epoch>}
    """
    secret = (settings.compat_endpoint.file_id_secret or "").encode()
    if len(secret) < 32:
        raise CompatBootError("file_id_secret missing or short")
    exp = int(time.time()) + int(settings.compat_endpoint.file_id_ttl_seconds)
    release_hash = hashlib.sha1((release_info or "").encode()).hexdigest()[:10]
    payload = {"p": provider, "i": str(native_id), "l": str(language),
               "r": release_hash, "exp": exp}
    p_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = _hmac_sign(secret, p_bytes)
    return base64.urlsafe_b64encode(p_bytes + b"." + sig).decode().rstrip("=")


def parse_file_id(token: str) -> Tuple[bool, dict]:
    try:
        padded = token + ("=" * (-len(token) % 4))
        raw = base64.urlsafe_b64decode(padded.encode())
        p_bytes, sig = raw.rsplit(b".", 1)
    except Exception:
        return False, {}
    secret = (settings.compat_endpoint.file_id_secret or "").encode()
    if len(secret) < 32:
        return False, {}
    expected_sig = _hmac_sign(secret, p_bytes)
    if not hmac.compare_digest(sig, expected_sig):
        return False, {}
    try:
        payload = json.loads(p_bytes)
    except ValueError:
        return False, {}
    if int(payload.get("exp", 0)) < int(time.time()):
        return False, {}
    return True, payload


def mint_stream_token(provider: str, native_id: str) -> str:
    """Short-lived HMAC token used in the /download/stream/<token> URL. 5-min default."""
    secret = (settings.compat_endpoint.file_id_secret or "").encode()
    exp = int(time.time()) + int(settings.compat_endpoint.stream_token_ttl_seconds)
    payload = {"p": provider, "i": str(native_id), "exp": exp, "t": "s"}
    p_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = _hmac_sign(secret, p_bytes)
    return base64.urlsafe_b64encode(p_bytes + b"." + sig).decode().rstrip("=")


def parse_stream_token(token: str) -> Tuple[bool, dict]:
    return parse_file_id(token)  # same structure; exp check included
