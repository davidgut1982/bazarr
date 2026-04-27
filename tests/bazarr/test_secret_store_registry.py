# coding=utf-8
"""Tests for bazarr.secrets.registry classification."""

from bazarr.secret_store.registry import (
    SYSTEM_SECRETS,
    USER_VISIBLE_SECRET_LISTS,
    USER_VISIBLE_SECRETS,
    is_system_secret,
    is_user_visible_secret,
    is_user_visible_secret_list,
)


def test_user_visible_includes_compat_token():
    """Per the user clarification - the compat endpoint TOKEN (the API
    token that gets pasted into VLSub / Jellyfin OS plugin) is visible
    on the frontend; only the compat endpoint's signing keys
    (jwt_secret, file_id_secret) stay backend-only."""
    assert is_user_visible_secret("compat_endpoint.token")
    assert is_system_secret("compat_endpoint.jwt_secret")
    assert is_system_secret("compat_endpoint.file_id_secret")


def test_user_visible_includes_arr_apikeys():
    for key in ("sonarr.apikey", "radarr.apikey", "jellyfin.apikey",
                "plex.apikey", "plex.token"):
        assert is_user_visible_secret(key), f"{key} should be user-visible"


def test_user_visible_includes_provider_passwords_and_keys():
    """Spot-check the provider list - if validators get added without
    updating the registry, those credentials would ship plaintext."""
    for key in ("opensubtitles.password", "addic7ed.password",
                "subdl.api_key", "subsource.apikey",
                "translator.openrouter_api_key", "translator.lingarr_token"):
        assert is_user_visible_secret(key), f"{key} should be user-visible"


def test_system_secrets_never_user_visible():
    """Disjoint sets - a secret cannot be both backend-only and visible."""
    overlap = USER_VISIBLE_SECRETS & SYSTEM_SECRETS
    assert not overlap, f"keys must not be in both tiers: {overlap}"
    overlap_lists = USER_VISIBLE_SECRET_LISTS & SYSTEM_SECRETS
    assert not overlap_lists, f"list keys must not be in SYSTEM: {overlap_lists}"


def test_system_includes_master_and_signing_keys():
    """Every cryptographic primitive (anything used to sign / encrypt
    OTHER secrets) must be SYSTEM, never visible to the frontend."""
    for key in ("general.flask_secret_key",
                "general.secrets_encryption_key",
                "compat_endpoint.jwt_secret",
                "compat_endpoint.file_id_secret",
                "plex.encryption_key",
                "translator.openrouter_encryption_key"):
        assert is_system_secret(key), f"{key} should be system-only"


def test_translator_gemini_keys_classified_as_list():
    """List-shaped credentials need a different code path (encrypt each
    element). Confirm they live in their own tier."""
    assert is_user_visible_secret_list("translator.gemini_keys")
    assert not is_user_visible_secret("translator.gemini_keys")


def test_unknown_keys_not_classified():
    """Defaults are 'no, this isn't a secret' - a brand-new setting must
    explicitly opt in or it stays plaintext (and the unit test for the
    next migration commit will catch that)."""
    assert not is_user_visible_secret("general.debug")
    assert not is_user_visible_secret("sonarr.url")
    assert not is_system_secret("general.port")
    assert not is_user_visible_secret_list("general.path_mappings")
