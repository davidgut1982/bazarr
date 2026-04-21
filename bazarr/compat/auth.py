from __future__ import annotations
import hmac
from bazarr.app.config import settings


def validate_compat_token(supplied: str | None) -> bool:
    """Constant-time compare against settings.compat_endpoint.token. Never `==`."""
    if not supplied:
        return False
    expected = settings.compat_endpoint.token or ""
    if not expected:
        return False
    return hmac.compare_digest(str(supplied), str(expected))
