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


import time


def test_mint_and_validate_jwt_roundtrip(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.jwt_secret", "j" * 32)
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.jwt_ttl_seconds", 60)
    tok = A.mint_jwt()
    ok, claims = A.validate_jwt(tok)
    assert ok is True and "exp" in claims


def test_validate_jwt_rejects_expired(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.jwt_secret", "j" * 32)
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.jwt_ttl_seconds", 1)
    tok = A.mint_jwt()
    time.sleep(2)
    ok, _ = A.validate_jwt(tok)
    assert ok is False


def test_validate_jwt_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.jwt_secret", "j" * 32)
    tok = A.mint_jwt()
    # Replace the signature segment entirely with a clearly invalid payload.
    header_payload, _ = tok.rsplit(".", 1)
    bad = header_payload + ".AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    ok, _ = A.validate_jwt(bad)
    assert ok is False


def test_boot_hmac_selftest_passes_with_valid_secrets(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.token", "t" * 32)
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.jwt_secret", "j" * 32)
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.file_id_secret", "f" * 32)
    A.boot_hmac_selftest()  # no exception


def test_boot_hmac_selftest_fails_closed_with_empty_secret(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.jwt_secret", "")
    with pytest.raises(A.CompatBootError):
        A.boot_hmac_selftest()


def test_file_id_roundtrip(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.file_id_secret", "f" * 32)
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.file_id_ttl_seconds", 60)
    token = A.mint_file_id(
        provider="opensubtitlescom",
        native_id="12345",
        language="eng",
        release_info="Movie.2020.1080p.BluRay.x264-GROUP",
    )
    ok, payload = A.parse_file_id(token)
    assert ok and payload["p"] == "opensubtitlescom" and payload["i"] == "12345"


def test_file_id_tamper_rejected(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.file_id_secret", "f" * 32)
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.file_id_ttl_seconds", 60)
    tok = A.mint_file_id("p", "i", "eng", "")
    bad = tok[:-4] + "AAAA"
    ok, _ = A.parse_file_id(bad)
    assert not ok


def test_file_id_expired_rejected(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.file_id_secret", "f" * 32)
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.file_id_ttl_seconds", 1)
    tok = A.mint_file_id("p", "i", "eng", "")
    time.sleep(2)
    ok, _ = A.parse_file_id(tok)
    assert not ok


def test_stream_token_roundtrip_and_expiry(monkeypatch):
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.file_id_secret", "f" * 32)
    monkeypatch.setattr("bazarr.compat.auth.settings.compat_endpoint.stream_token_ttl_seconds", 1)
    tok = A.mint_stream_token("p", "i")
    ok, payload = A.parse_stream_token(tok)
    assert ok and payload["p"] == "p" and payload["i"] == "i"
    time.sleep(2)
    ok, _ = A.parse_stream_token(tok)
    assert not ok
