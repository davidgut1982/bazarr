from flask import Flask
import pytest


def test_disabled_state_404s_json(monkeypatch):
    """enabled=False: all /api/v1/* return stub JSON 404."""
    from bazarr.compat import register
    monkeypatch.setattr("bazarr.app.config.settings.compat_endpoint.enabled", False)
    app = Flask(__name__)
    register(app, base_url="")
    r = app.test_client().get("/api/v1/subtitles")
    assert r.status_code == 404
    assert r.headers["x-reason"] == "compat-disabled"


def test_enabled_state_aborts_when_secrets_missing(monkeypatch):
    """enabled=True without valid secrets -> CompatBootError (fail-closed, B6)."""
    from bazarr.compat import register
    from bazarr.compat.auth import CompatBootError
    monkeypatch.setattr("bazarr.app.config.settings.compat_endpoint.enabled", True)
    monkeypatch.setattr("bazarr.app.config.settings.compat_endpoint.token", "")
    app = Flask(__name__)
    with pytest.raises(CompatBootError):
        register(app, base_url="")
