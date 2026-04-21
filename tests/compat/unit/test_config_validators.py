import os
import tempfile

import pytest
import yaml
from dynaconf import Dynaconf
from dynaconf.validator import ValidationError

# Pull the real validators list from the application config module.
# This is the source of truth: the same Validator objects registered
# into the production `settings` singleton at startup.
from bazarr.app.config import validators as app_validators


def _compat_validators():
    """Return only the compat_endpoint validators from the real config list."""
    return [
        v for v in app_validators
        if any("compat_endpoint" in name for name in v.names)
    ]


def _make_settings(config_data: dict) -> Dynaconf:
    """
    Create a fresh, isolated Dynaconf instance loaded from a temp YAML file
    and pre-registered with the real compat_endpoint validators from config.py.

    Each call returns a new instance, so tests cannot leak state to one another
    or to the module-level `settings` singleton.
    """
    tmp_dir = tempfile.mkdtemp()
    cfg_path = os.path.join(tmp_dir, "config.yaml")
    with open(cfg_path, "w") as f:
        yaml.dump(config_data, f)
    s = Dynaconf(settings_file=cfg_path, core_loaders=["YAML"], apply_default_on_none=True)
    s.validators.register(*_compat_validators())
    return s


# ---------------------------------------------------------------------------
# Default / disabled state
# ---------------------------------------------------------------------------

def test_defaults_when_no_config_present():
    """An empty config file uses validator defaults: enabled=False, secrets empty.
    No ValidationError should be raised."""
    tmp_dir = tempfile.mkdtemp()
    cfg_path = os.path.join(tmp_dir, "config.yaml")
    open(cfg_path, "w").close()  # empty file

    s = Dynaconf(settings_file=cfg_path, core_loaders=["YAML"], apply_default_on_none=True)
    s.validators.register(*_compat_validators())

    # Must not raise: disabled + empty secrets is valid
    s.validators.validate_all()
    assert s.compat_endpoint.enabled is False


def test_disabled_with_empty_secrets_passes():
    """When enabled=False, all three secrets may be empty without triggering
    the conditional must_exist / len_min validators."""
    s = _make_settings({
        "compat_endpoint": {
            "enabled": False,
            "token": "",
            "jwt_secret": "",
            "file_id_secret": "",
        }
    })
    s.validators.validate_all()  # must not raise
    assert s.compat_endpoint.enabled is False


# ---------------------------------------------------------------------------
# Enabled: each secret individually missing / too short
# ---------------------------------------------------------------------------

def test_enabled_empty_jwt_secret_raises():
    """When enabled=True, an empty jwt_secret must trigger a ValidationError
    from the conditional len_min=32 validator at config.py:498-502."""
    s = _make_settings({
        "compat_endpoint": {
            "enabled": True,
            "token": "a" * 32,
            "jwt_secret": "",
            "file_id_secret": "c" * 32,
        }
    })
    with pytest.raises(ValidationError):
        s.validators.validate_all()


def test_enabled_token_too_short_raises():
    """When enabled=True, a token shorter than 32 characters must trigger a
    ValidationError from the conditional len_min=32 validator at config.py:493-497."""
    s = _make_settings({
        "compat_endpoint": {
            "enabled": True,
            "token": "short",
            "jwt_secret": "b" * 32,
            "file_id_secret": "c" * 32,
        }
    })
    with pytest.raises(ValidationError):
        s.validators.validate_all()


def test_enabled_empty_file_id_secret_raises():
    """When enabled=True, an empty file_id_secret must trigger a ValidationError
    from the conditional len_min=32 validator at config.py:503-507."""
    s = _make_settings({
        "compat_endpoint": {
            "enabled": True,
            "token": "a" * 32,
            "jwt_secret": "b" * 32,
            "file_id_secret": "",
        }
    })
    with pytest.raises(ValidationError):
        s.validators.validate_all()


# ---------------------------------------------------------------------------
# Enabled: all secrets valid
# ---------------------------------------------------------------------------

def test_enabled_all_secrets_valid_passes():
    """When enabled=True and all three secrets are at least 32 characters,
    validation must succeed without raising."""
    s = _make_settings({
        "compat_endpoint": {
            "enabled": True,
            "token": "a" * 32,
            "jwt_secret": "b" * 32,
            "file_id_secret": "c" * 32,
        }
    })
    s.validators.validate_all()  # must not raise
    assert s.compat_endpoint.enabled is True
