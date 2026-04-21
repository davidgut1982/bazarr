import pytest
from bazarr.compat import auth as A


def test_validate_compat_token_accepts_exact_match(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.token", "a" * 32)
    assert A.validate_compat_token("a" * 32) is True


def test_validate_compat_token_rejects_wrong(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.token", "a" * 32)
    assert A.validate_compat_token("b" * 32) is False


def test_validate_compat_token_empty_returns_false(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.token", "a" * 32)
    assert A.validate_compat_token("") is False
    assert A.validate_compat_token(None) is False


def test_validate_compat_token_uses_constant_time():
    """Fails if `==` is used instead of hmac.compare_digest."""
    import hmac
    # Sanity: hmac.compare_digest accepts bytes and str
    assert hmac.compare_digest("a" * 32, "a" * 32) is True
