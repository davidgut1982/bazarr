import pytest
from flask import Flask


API_KEY = "t" * 32
JWT_SECRET = "j" * 32
FID_SECRET = "f" * 32


@pytest.fixture(autouse=True)
def _secrets():
    from app.config import settings
    from compat import jwt_denylist
    settings["compat_endpoint"]["token"] = API_KEY
    settings["compat_endpoint"]["jwt_secret"] = JWT_SECRET
    settings["compat_endpoint"]["file_id_secret"] = FID_SECRET
    settings["compat_endpoint"]["jwt_ttl_seconds"] = 3600
    jwt_denylist.reset()
    yield
    jwt_denylist.reset()


def _app():
    from compat.routes import compat_bp
    app = Flask(__name__)
    app.register_blueprint(compat_bp, url_prefix="/api/v1")
    return app


def test_logout_revokes_jwt():
    from compat import auth
    c = _app().test_client()
    tok = auth.mint_jwt()

    # JWT works initially on a require_jwt route.
    r = c.post("/api/v1/download",
               headers={"Api-Key": API_KEY, "Authorization": f"Bearer {tok}"},
               json={"file_id": 999})
    # Any status except 401 means auth passed (404 is expected for unknown fid).
    assert r.status_code != 401

    # Logout revokes it.
    r = c.delete("/api/v1/logout",
                 headers={"Api-Key": API_KEY,
                          "Authorization": f"Bearer {tok}"})
    assert 200 <= r.status_code < 300

    # Same JWT is now rejected.
    r = c.post("/api/v1/download",
               headers={"Api-Key": API_KEY, "Authorization": f"Bearer {tok}"},
               json={"file_id": 1})
    assert r.status_code == 401


def test_logout_requires_bearer():
    """Without a Bearer the route returns 401; the contract doc's
    'any 2xx without bearer' is removed because revocation needs the jti."""
    c = _app().test_client()
    r = c.delete("/api/v1/logout", headers={"Api-Key": API_KEY})
    assert r.status_code == 401
