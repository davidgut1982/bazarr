from __future__ import annotations
import logging
from threading import Lock
from typing import Iterable
from urllib.parse import quote
from babelfish import Language
from subliminal.video import Episode, Movie, Video
from subliminal_patch.core_persistent import list_all_subtitles_parallel

from bazarr.app.config import settings
from bazarr.app.get_providers import get_providers_sorted, get_providers_auth
from bazarr.compat import auth, cache as C, response_mapper as M
from bazarr.utilities.url_guard import assert_safe_outbound, UnsafeURLError

logger = logging.getLogger("bazarr.compat.service")

_pool_lock = Lock()
_compat_pool = None  # lazy singleton, dedicated (B2)


def _get_compat_pool():
    """Dedicated SZAsyncProviderPool instance. MUST NOT share app.get_providers._pools."""
    global _compat_pool
    with _pool_lock:
        if _compat_pool is None:
            from subliminal_patch.core import SZAsyncProviderPool
            _compat_pool = SZAsyncProviderPool(
                providers=get_providers_sorted(),
                provider_configs=get_providers_auth(),
                blacklist=None,
                ban_list=None,
                language_hook=None,
                language_equals=[],
            )
        return _compat_pool


def reset_compat_pool() -> None:
    """Called on settings-change or provider toggle so stale creds don't persist."""
    global _compat_pool
    with _pool_lock:
        _compat_pool = None


def _build_video(imdb_id: str, season: int | None, episode: int | None,
                 media_type: str) -> Video:
    """No filesystem, no parse_video, no scan_video."""
    if media_type == "episode":
        v = Episode(
            name=f"virtual_{imdb_id}_s{season}e{episode}.mkv",
            series="",
            season=int(season or 0),
            episode=int(episode or 0),
            series_imdb_id=imdb_id,
        )
    else:
        v = Movie(
            name=f"virtual_{imdb_id}.mkv",
            title="",
            year=None,
            imdb_id=imdb_id,
        )
    v.size = None
    v.hashes = {}
    return v


def _do_fanout(imdb_id, season, episode, languages, media_type):
    pool = _get_compat_pool()
    video = _build_video(imdb_id, season, episode, media_type)
    results = list_all_subtitles_parallel(
        [video], set(languages), pool,
        per_provider_timeout=int(settings.compat_endpoint.per_provider_timeout_seconds),
        wall_timeout=int(settings.compat_endpoint.search_timeout_seconds),
    )
    subs = []
    for v, sub_list in results.items():
        subs.extend(sub_list)
    entries = []
    for sub in subs:
        file_id = auth.mint_file_id(
            provider=getattr(sub, "provider_name", "unknown"),
            native_id=getattr(sub, "id", ""),
            language=str(getattr(sub, "language", "")),
            release_info=getattr(sub, "release_info", "") or "",
            subtitle=sub,
        )
        entries.append(M.subtitle_to_os_entry(sub, file_id, media_type, imdb_id,
                                              season, episode))
    entries.sort(key=lambda e: -int(e["attributes"].get("download_count", 0)))
    return M.search_envelope(entries, per_page=50, page=1)


def search(imdb_id: str, season, episode, languages: Iterable[Language],
           media_type: str) -> dict:
    enabled = get_providers_sorted()
    key = C.build_key(media_type, imdb_id, season, episode, languages, enabled)
    ttl = int(settings.compat_endpoint.cache_ttl_seconds)
    return C.compat_region.get_or_create(
        key,
        creator=lambda: _do_fanout(imdb_id, season, episode, languages, media_type),
        expiration_time=ttl,
    )


def download(file_id, base_host: str = "") -> dict:
    """Resolve the int file_id, mint a short-lived stream token, return a
    download link. No provider fetch happens here - the subtitle is fetched
    only when the client follows the link.

    The link is relative by default (starts with `/api/v1/...`) because
    Bazarr+ can't reliably determine its own public URL behind its supervisor
    proxy. Clients already know the host they connected to. Pass base_host
    to override for callers that want an absolute URL.
    """
    ok, _payload = auth.parse_file_id(file_id)
    if not ok:
        raise FileNotFoundError("file_id invalid or expired")
    stream_tok = auth.mint_file_stream_token(int(file_id))
    path = f"/api/v1/download/stream/{quote(stream_tok, safe='')}"
    link = f"{base_host.rstrip('/')}{path}" if base_host else path
    return M.download_response(link)


def _fetch_subtitle_bytes(sub) -> bytes:
    """SSRF-guard the provider URL and invoke pool.download_subtitle(sub).

    `sub` is the original Subtitle instance retained from search (stashed in
    the file_id store). Downloading via the pool is the only portable path:
    each provider's `download_subtitle(sub)` knows exactly how to resolve its
    own subtitle's URL, auth, and content encoding - most providers do not
    expose a generic `get_subtitle_by_id` method.
    """
    if sub is None:
        raise FileNotFoundError("subtitle payload missing")

    # SSRF guard: only apply when download_link/url is a full http(s) URL.
    # Many providers store an internal reference (native id, zip name, etc.)
    # in these fields and construct the actual fetch URL inside their own
    # download_subtitle(). Running the guard on a non-URL string would reject
    # perfectly legitimate providers for the wrong reason.
    url = getattr(sub, "download_link", None) or getattr(sub, "url", None)
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        assert_safe_outbound(url)  # raises UnsafeURLError on private/loopback/etc.

    provider_name = getattr(sub, "provider_name", None)
    if not provider_name:
        raise FileNotFoundError("subtitle has no provider_name")

    pool = _get_compat_pool()
    try:
        pool.download_subtitle(sub)
    except Exception as e:
        logger.exception("compat: download_subtitle failed for %s: %s",
                         provider_name, e)
        raise
    content = getattr(sub, "content", None)
    if not content:
        raise FileNotFoundError(
            f"provider {provider_name!r} returned empty content for subtitle"
        )
    return content


def serve_subtitle_content(stream_token: str) -> tuple[bytes, str]:
    """Validate the stream token and return the subtitle bytes + content-type.

    Raises:
        ValueError: stream token invalid or expired
        FileNotFoundError: subtitle not found
        UnsafeURLError: provider URL failed SSRF guard
    """
    ok, payload = auth.parse_file_stream_token(stream_token)
    if not ok:
        raise ValueError("stream token invalid or expired")
    fid = payload.get("fid")
    if fid is None:
        raise ValueError("stream token missing file_id")
    ok, fpayload = auth.parse_file_id(fid)
    if not ok:
        raise FileNotFoundError("file_id expired or not found")
    sub = fpayload.get("sub")
    # Surface the guard symbol so tests can patch it.
    _ = assert_safe_outbound
    blob = _fetch_subtitle_bytes(sub)
    return blob, "application/x-subrip"


def guessit_filename(filename: str) -> dict:
    """Thin wrapper over guessit. Returns a JSON-safe dict.

    Rejects null bytes and filenames >512 chars (defense against path abuse).
    """
    if not filename or "\x00" in filename:
        raise ValueError("filename contains null byte or is empty")
    if len(filename) > 512:
        raise ValueError("filename too long")
    from subliminal_patch.core import guessit as _guessit
    result = _guessit(filename)
    # guessit returns a MatchesDict; coerce to plain dict with JSON-friendly values.
    import json
    from guessit.jsonutils import GuessitEncoder
    return json.loads(json.dumps(dict(result), cls=GuessitEncoder))
