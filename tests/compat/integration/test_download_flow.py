from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def _set_secrets(monkeypatch):
    from bazarr.app.config import settings
    monkeypatch.setattr(settings.compat_endpoint, "file_id_secret", "f" * 32)
    monkeypatch.setattr(settings.compat_endpoint, "file_id_ttl_seconds", 3600)
    monkeypatch.setattr(settings.compat_endpoint, "stream_token_ttl_seconds", 300)


def test_download_returns_link_without_provider_fetch():
    from bazarr.compat import service, auth

    fid = auth.mint_file_id("opensubtitlescom", "123", "eng", "")
    resp = service.download(fid, base_host="http://bazarr.local")
    assert resp["link"].startswith("http://bazarr.local/api/v1/download/stream/")
    assert resp["remaining_downloads"] > 0


def test_download_rejects_invalid_file_id():
    from bazarr.compat import service
    with pytest.raises(FileNotFoundError):
        service.download("not-a-real-token", base_host="http://bazarr.local")
