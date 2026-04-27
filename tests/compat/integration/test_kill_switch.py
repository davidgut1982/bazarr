from flask import Flask
from compat.routes import compat_stub_bp


def test_stub_returns_json_404_with_x_reason():
    app = Flask(__name__)
    app.register_blueprint(compat_stub_bp, url_prefix="/api/v1")
    for path in ("/api/v1/subtitles", "/api/v1/login", "/api/v1/anything"):
        r = app.test_client().get(path)
        assert r.status_code == 404
        assert r.headers["Content-Type"] == "application/json"
        assert r.headers.get("x-reason") == "compat-disabled"
        assert r.json == {"message": "disabled"}
