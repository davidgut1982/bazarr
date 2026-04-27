# coding=utf-8
"""Bidirectional secret crossing between in-memory plaintext and on-disk
ciphertext.

The model:
- In memory (`settings.sonarr.apikey`, etc.): always plaintext. Application
  code reads creds the same way it always has.
- On disk (`config.yaml`): always ciphertext, post-migration. The first-
  boot-after-upgrade path is plaintext; the bootstrap decrypter is a
  passthrough on plaintext (`decrypt_secret` returns plaintext unchanged
  when the marker prefix is missing) and the next `write_config()`
  rewrites the file in encrypted form. Auto-migration is implicit -
  there is no separate one-shot script.

Two boundaries:
1. After dynaconf finishes loading config.yaml: walk USER_VISIBLE_SECRETS
   and decrypt anything carrying the marker prefix. After this runs, the
   live settings object holds plaintext for every credential.
2. Inside `write_config()`: snapshot settings as a dict, encrypt every
   USER_VISIBLE_SECRETS in the snapshot, persist that. Only the
   snapshot is encrypted; the live settings object stays plaintext.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict

from .crypto import decrypt_secret, encrypt_secret, is_encrypted
from .registry import USER_VISIBLE_SECRET_LISTS, USER_VISIBLE_SECRETS

logger = logging.getLogger(__name__)


def _split_path(path: str) -> tuple[str, str]:
    """Split 'section.key' into ('section', 'key'). Always yields exactly
    two parts because the registry keys are flat dotted paths by contract."""
    section, _, key = path.partition(".")
    if not key:
        raise ValueError(f"Registry path {path!r} must be 'section.key'")
    return section, key


def _read_section_key(d: Dict[str, Any], path: str) -> tuple[str, str, Any]:
    """Look up `section.key` in a dict whose top-level keys may be either
    case. Returns (section_lookup_key, attr_key, value) or raises KeyError.
    """
    section, key = _split_path(path)
    # Settings dicts have section keys in mixed case depending on origin;
    # match either casing without rewriting the dict.
    for candidate in (section, section.lower(), section.upper()):
        if candidate in d and isinstance(d[candidate], dict) and key in d[candidate]:
            return candidate, key, d[candidate][key]
    raise KeyError(path)


def decrypt_settings_in_place(settings_obj) -> None:
    """Walk every USER_VISIBLE_SECRETS / USER_VISIBLE_SECRET_LISTS path in
    the live settings object and decrypt any value carrying the marker
    prefix. Plaintext values are left untouched (decrypt_secret is a
    passthrough on plaintext - that's the auto-migration story).

    Failures are logged but non-fatal: a corrupt single ciphertext should
    not stop bazarr from starting. The operator can rotate that credential
    via the Settings page; everything else continues to work.

    Runs exactly once at bootstrap, after settings.validators.validate_all
    finishes. Re-running is harmless (decrypt_secret is idempotent on
    already-plaintext values).
    """
    for path in USER_VISIBLE_SECRETS:
        try:
            section, key = _split_path(path)
            section_obj = getattr(settings_obj, section, None)
            if section_obj is None:
                continue
            current = section_obj.get(key) if hasattr(section_obj, "get") \
                else getattr(section_obj, key, None)
            if isinstance(current, str) and is_encrypted(current):
                decrypted = decrypt_secret(current)
                section_obj[key] = decrypted
        except Exception as e:
            # Don't print the credential value or section/key hint that could
            # be inferred to a specific provider in a public bug report.
            logger.error(
                f"Failed to decrypt secret at rest: {type(e).__name__}; "
                f"continuing with the value unchanged so the rest of bazarr "
                f"can boot. Rotate the credential to recover."
            )

    for path in USER_VISIBLE_SECRET_LISTS:
        try:
            section, key = _split_path(path)
            section_obj = getattr(settings_obj, section, None)
            if section_obj is None:
                continue
            current = section_obj.get(key) if hasattr(section_obj, "get") \
                else getattr(section_obj, key, None)
            if not isinstance(current, list):
                continue
            new_items = []
            for item in current:
                if isinstance(item, str) and is_encrypted(item):
                    new_items.append(decrypt_secret(item))
                else:
                    new_items.append(item)
            section_obj[key] = new_items
        except Exception as e:
            logger.error(
                f"Failed to decrypt list-shaped secret at rest: "
                f"{type(e).__name__}; continuing unchanged."
            )


def encrypt_settings_dict(plaintext_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dict identical to `plaintext_dict` except that every
    USER_VISIBLE_SECRETS / USER_VISIBLE_SECRET_LISTS path is encrypted.

    Used by `write_config()` to produce the on-disk form. The dict is
    deep-copied so the in-memory settings (which is what the caller
    snapshots) is never mutated to ciphertext.

    Already-encrypted values are returned unchanged (encrypt_secret is
    idempotent on its own ciphertext) - that handles the case where a
    config save races with a fresh load and the live settings already
    carry marker prefixes.
    """
    out = deepcopy(plaintext_dict)
    for path in USER_VISIBLE_SECRETS:
        try:
            section_key, attr, value = _read_section_key(out, path)
            if isinstance(value, str) and value:
                out[section_key][attr] = encrypt_secret(value)
        except KeyError:
            continue

    for path in USER_VISIBLE_SECRET_LISTS:
        try:
            section_key, attr, value = _read_section_key(out, path)
            if isinstance(value, list):
                out[section_key][attr] = [
                    encrypt_secret(v) if isinstance(v, str) and v else v
                    for v in value
                ]
        except KeyError:
            continue
    return out


def decrypt_settings_dict(encrypted_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Symmetric counterpart of encrypt_settings_dict. Returns a new dict
    where every USER_VISIBLE_SECRETS / USER_VISIBLE_SECRET_LISTS path is
    decrypted to plaintext.

    Used by `write_config()` to compare the in-memory plaintext settings
    against the on-disk dict in plaintext form. Without this normalization
    the comparison would always differ (encrypt_secret is non-deterministic
    by design), and write_config would rewrite the file on every save
    even when nothing changed.

    Decrypt failures (corrupt cipher, wrong master key) leave the value
    untouched so the comparison fails safely - the rewrite proceeds and
    overwrites the bad cipher with a fresh one.
    """
    out = deepcopy(encrypted_dict)
    for path in USER_VISIBLE_SECRETS:
        try:
            section_key, attr, value = _read_section_key(out, path)
            if isinstance(value, str) and is_encrypted(value):
                try:
                    out[section_key][attr] = decrypt_secret(value)
                except ValueError:
                    pass  # leave the bad cipher in place; compare will diff
        except KeyError:
            continue

    for path in USER_VISIBLE_SECRET_LISTS:
        try:
            section_key, attr, value = _read_section_key(out, path)
            if isinstance(value, list):
                new_items = []
                for v in value:
                    if isinstance(v, str) and is_encrypted(v):
                        try:
                            new_items.append(decrypt_secret(v))
                        except ValueError:
                            new_items.append(v)
                    else:
                        new_items.append(v)
                out[section_key][attr] = new_items
        except KeyError:
            continue
    return out
