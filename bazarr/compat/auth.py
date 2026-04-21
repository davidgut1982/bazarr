from __future__ import annotations
import hashlib
import hmac
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
