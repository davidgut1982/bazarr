# bazarr/compat/__init__.py
"""Bazarr+ OpenSubtitles-compatible REST endpoint subpackage.

DO NOT import from bazarr.subtitles.manual, bazarr.subtitles.indexer, or
TableEpisodes/TableMovies. The compat surface is isolated from DB-backed
media objects by design.
"""
from __future__ import annotations


def register(app, base_url: str) -> None:
    """Register the compat blueprint (real or stub) with the Flask app.

    MUST be called BEFORE api_bp registration to preserve route precedence.
    """
    from bazarr.app.config import settings
    enabled = bool(settings.compat_endpoint.enabled)
    if enabled:
        from .routes import compat_bp
    else:
        from .routes import compat_stub_bp as compat_bp
    app.register_blueprint(compat_bp, url_prefix=(base_url.rstrip("/") + "/api/v1"))
