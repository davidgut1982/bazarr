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


def _lookup_library_metadata(imdb_id: str, media_type: str) -> dict:
    """Best-effort title/year/tvdb_id resolution from the local Bazarr DB.

    Providers like supersubtitles and yifysubtitles score heavily on title
    match, so searching with a bare `imdb_id` and empty title returns few or
    irrelevant results. When the title is already in TableMovies/TableShows
    (almost always, since this is a library-backed deployment) we can hand
    the real title/year to the Video constructor and dramatically improve
    hit rate. Returns {} if the imdb_id is not in the library.
    """
    try:
        from bazarr.app.database import database, select, TableMovies, TableShows
    except Exception:
        return {}
    imdb = imdb_id if str(imdb_id).startswith("tt") else f"tt{imdb_id}"
    try:
        if media_type == "episode":
            row = database.execute(
                select(TableShows.title, TableShows.year, TableShows.tvdbId)
                .where(TableShows.imdbId == imdb)
            ).first()
            if row:
                return {"title": row[0] or "", "year": row[1],
                        "tvdb_id": row[2]}
        else:
            row = database.execute(
                select(TableMovies.title, TableMovies.year)
                .where(TableMovies.imdbId == imdb)
            ).first()
            if row:
                return {"title": row[0] or "", "year": row[1]}
    except Exception as e:
        logger.debug("compat library metadata lookup failed for %s: %s", imdb, e)
    return {}


def _guessit_filename(filename: str) -> dict:
    """Run guessit on a filename and return a plain dict of the interesting
    fields. Isolated from subliminal's Video.fromname so it doesn't raise
    when the type disagrees with what the client told us."""
    if not filename:
        return {}
    try:
        from subliminal_patch.core import guessit as _guessit
        g = _guessit(filename)
        return dict(g) if g else {}
    except Exception as e:
        logger.debug("compat guessit failed on %r: %s", filename, e)
        return {}


def _build_video(imdb_id: str, season: int | None, episode: int | None,
                 media_type: str, query: str | None = None,
                 moviehash: str | None = None) -> Video:
    """Construct a Video for compat fanout, enriched with whatever we can
    scrape from (a) the local library (title/year/tvdb_id), (b) the client's
    filename via guessit (source, resolution, release_group, codecs), and
    (c) the OS-style moviehash if the client has one. Providers score
    heavily on these fields, so populating them dramatically improves hit
    rates for file-less compat searches.
    """
    meta = _lookup_library_metadata(imdb_id, media_type)
    title = meta.get("title") or ""
    year_raw = meta.get("year")
    try:
        year = int(str(year_raw)[:4]) if year_raw else None
    except (TypeError, ValueError):
        year = None

    g = _guessit_filename(query) if query else {}
    # guessit may expose 'title' in a different shape than our library; prefer
    # the library title when both exist because it's been curated.
    g_title = g.get("title") or ""
    g_year = g.get("year")
    g_source = g.get("source")
    g_release_group = g.get("release_group")
    g_resolution = g.get("screen_size") or g.get("resolution")
    g_video_codec = g.get("video_codec")
    g_audio_codec = g.get("audio_codec")

    # Prefer the client's filename (it carries release info) as the Video.name,
    # since many providers match subtitle names against it fuzzily.
    name_fallback = query or None

    # Title precedence: library (curated) > refiner (OMDB/TVDB) > guessit.
    # guessit titles are unreliable noise when the filename is bad, so we
    # only fall back to them as a last resort.
    if media_type == "episode":
        name = name_fallback or (
            f"{title or g_title or imdb_id}.S{int(season or 0):02d}E{int(episode or 0):02d}.mkv"
        )
        v = Episode(
            name=name,
            series=title,  # will be filled by refiner then guessit if empty
            season=int(season or 0),
            episode=int(episode or 0),
            series_imdb_id=imdb_id,
            year=year,
            source=g_source,
            release_group=g_release_group,
            resolution=g_resolution,
            video_codec=g_video_codec,
            audio_codec=g_audio_codec,
        )
        tvdb_id = meta.get("tvdb_id")
        if tvdb_id:
            try:
                v.series_tvdb_id = int(tvdb_id)
            except (TypeError, ValueError):
                pass
    else:
        name = name_fallback or (
            f"{title or imdb_id}.{year}.mkv" if year
            else f"{title or imdb_id}.mkv"
        )
        v = Movie(
            name=name,
            title=title,  # will be filled by refiner then guessit if empty
            year=year,
            imdb_id=imdb_id,
            source=g_source,
            release_group=g_release_group,
            resolution=g_resolution,
            video_codec=g_video_codec,
            audio_codec=g_audio_codec,
        )
    v.size = None
    # OpenSubtitles uses a specific file-hash algorithm; if the client
    # computed and provided it, OS providers get an exact-hash match path.
    if moviehash:
        v.hashes = {"opensubtitles": str(moviehash), "opensubtitlescom": str(moviehash)}
    else:
        v.hashes = {}

    # Library miss -> try OMDB/TVDB refiners (network, best-effort).
    if not getattr(v, "title", None) and not getattr(v, "series", None):
        _refine_from_imdb(v, media_type)

    # Refiner miss -> last-resort guessit title. Do NOT clobber a real value.
    if media_type == "episode":
        if not getattr(v, "series", None) and g_title:
            v.series = g_title
    else:
        if not getattr(v, "title", None) and g_title:
            v.title = g_title
    if not getattr(v, "year", None) and g_year:
        v.year = g_year
    return v


def _refine_from_imdb(video, media_type: str) -> None:
    """Best-effort network lookup to populate title/year/tvdb_id when the
    local library doesn't know the imdb_id. Swallows all exceptions.

    We bypass subliminal's stock refiners for movies: they early-exit when
    video.imdb_id is set (which it always is from our compat clients),
    treating it as 'information complete' even when the title is still
    empty. For episodes, we also query TVDB directly by imdb_id because
    the stock TVDB refiner requires a series name we don't have.
    """
    if media_type == "episode":
        _tvdb_lookup_by_imdb(video)
    else:
        _omdb_lookup_by_imdb(video)


def _omdb_lookup_by_imdb(video) -> None:
    """Query OMDB by imdb_id directly (`?i=tt...`) and populate title/year.
    Requires settings.omdb.apikey or OMDB_API_KEY env. No-op without a key."""
    try:
        from subliminal_patch.refiners.omdb import _resolve_omdb_apikey
        apikey = _resolve_omdb_apikey()
        if not apikey:
            return
        imdb = getattr(video, "imdb_id", None)
        if not imdb:
            return
        import requests
        r = requests.get("http://www.omdbapi.com/",
                         params={"i": imdb, "apikey": apikey},
                         timeout=5)
        if r.status_code != 200:
            return
        data = r.json()
        if data.get("Response") != "True":
            return
        if not getattr(video, "title", None):
            video.title = data.get("Title") or ""
        if not getattr(video, "year", None):
            try:
                video.year = int(str(data.get("Year", ""))[:4])
            except (TypeError, ValueError):
                pass
    except Exception as e:
        logger.debug("compat OMDB-by-imdb lookup failed: %s", e)


def _tvdb_lookup_by_imdb(video) -> None:
    """Query TVDB with series_imdb_id (not series name). Populates
    video.series_tvdb_id, video.series, video.year and the episode's tvdb_id
    when available. Subliminal's stock TVDB refiner requires a series name,
    which we don't have on library miss."""
    try:
        from subliminal.refiners.tvdb import tvdb_client, get_series_episode
        imdb = getattr(video, "series_imdb_id", None) or getattr(video, "imdb_id", None)
        if not imdb:
            return
        results = tvdb_client.search_series(imdb_id=imdb)
        if not results:
            return
        series = results[0]
        tvdb_id = series.get("id")
        if not tvdb_id:
            return
        video.series_tvdb_id = int(tvdb_id)
        if not getattr(video, "series", None):
            video.series = series.get("seriesName") or ""
        first_aired = series.get("firstAired") or ""
        if first_aired and not getattr(video, "year", None):
            try:
                video.year = int(first_aired[:4])
            except (TypeError, ValueError):
                pass
        if getattr(video, "season", None) and getattr(video, "episode", None):
            ep = get_series_episode(tvdb_id, int(video.season), int(video.episode))
            if ep:
                if not getattr(video, "tvdb_id", None):
                    video.tvdb_id = ep.get("id")
                if not getattr(video, "title", None):
                    video.title = ep.get("episodeName") or None
    except Exception as e:
        logger.debug("compat TVDB-by-imdb lookup failed: %s", e)


# Providers whose check() passes for a virtual video but that physically
# cannot produce results without the file on disk. Skipping them at fanout
# time frees a thread-pool slot and cuts wall time.
_SKIP_FOR_VIRTUAL_VIDEO = frozenset({"embeddedsubtitles"})


def _do_fanout(imdb_id, season, episode, languages, media_type,
               query=None, moviehash=None):
    pool = _get_compat_pool()
    video = _build_video(imdb_id, season, episode, media_type,
                         query=query, moviehash=moviehash)
    logger.info("compat fanout: video=%r lang=%s providers=%d",
                video, [str(l) for l in languages], len(pool.providers))
    results = list_all_subtitles_parallel(
        [video], set(languages), pool,
        per_provider_timeout=int(settings.compat_endpoint.per_provider_timeout_seconds),
        wall_timeout=int(settings.compat_endpoint.search_timeout_seconds),
        exclude_providers=_SKIP_FOR_VIRTUAL_VIDEO,
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
           media_type: str, query: str | None = None,
           moviehash: str | None = None) -> dict:
    enabled = get_providers_sorted()
    key = C.build_key(media_type, imdb_id, season, episode, languages, enabled,
                      query=query, moviehash=moviehash)
    ttl = int(settings.compat_endpoint.cache_ttl_seconds)
    return C.compat_region.get_or_create(
        key,
        creator=lambda: _do_fanout(imdb_id, season, episode, languages,
                                    media_type, query=query, moviehash=moviehash),
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
