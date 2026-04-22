from __future__ import annotations
from flask import Blueprint, request, jsonify, Response
from bazarr.compat.auth import compat_error

compat_stub_bp = Blueprint("compat_stub", __name__)


@compat_stub_bp.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@compat_stub_bp.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def _all_disabled(path):
    return compat_error("disabled", 404, "compat-disabled")


from bazarr.compat import auth, service, response_mapper as M
from bazarr.compat.auth import compat_auth

compat_bp = Blueprint("compat", __name__)


@compat_bp.after_request
def _strip_cors(resp):
    """Explicit CORS scope override (B4). No CORS for /api/v1/*."""
    for h in ("Access-Control-Allow-Origin", "Access-Control-Allow-Credentials",
              "Access-Control-Allow-Methods", "Access-Control-Allow-Headers"):
        resp.headers.pop(h, None)
    return resp


def _infer_client_base(req) -> tuple[str, str]:
    """Best-effort (scheme, host) reconstruction for the URL the client hit.

    Honors proxy headers first (reverse-proxy or supervisor setups), falls back
    to request.host/scheme. Returns ("", "") if only the internal loopback
    address is visible - callers should then emit a relative URL.
    """
    scheme = (req.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip() or req.scheme
    host = (req.headers.get("X-Forwarded-Host") or "").split(",")[0].strip() or req.host
    # Ignore the internal supervisor host; it's meaningless to clients.
    if not host or host.startswith("127.") or host.startswith("localhost"):
        return "", ""
    return scheme or "http", host


@compat_bp.route("/login", methods=["POST"])
@compat_auth(require_jwt=False)
def login():
    # OS.com returns base_url as a bare hostname (no scheme). We try forwarded
    # headers first, then request.host; when the client's real host is unknown
    # (e.g. a bare LAN probe with no reverse proxy) we return request.host as-is
    # for compatibility - clients can still use the token and JWT.
    scheme, host = _infer_client_base(request)
    base_url = host or request.host
    return jsonify({
        "token": auth.mint_jwt(),
        "status": 200,
        "base_url": base_url,
        "user": M.user_info_response()["data"],
    })


@compat_bp.route("/logout", methods=["DELETE"])
@compat_auth(require_jwt=True)
def logout():
    return "", 204


@compat_bp.route("/subtitles", methods=["GET"])
@compat_auth(require_jwt=False)
def subtitles():
    args = request.args
    langs_s = args.get("languages") or ""
    imdb = args.get("imdb_id") or args.get("tmdb_id") or args.get("query")
    if not imdb:
        return compat_error("imdb_id, tmdb_id, or query required", 400, "bad-request")
    # subzero.language.Language (what every bazarr provider compares with).
    # babelfish.Language does NOT equal the subzero subclass in set operations
    # even though hash() matches, so providers would skip every language.
    from subzero.language import Language
    try:
        if langs_s:
            langs = [Language.fromietf(c.strip()) for c in langs_s.split(",") if c.strip()]
        else:
            # OS.com accepts no-language searches. Fall back to the enabled
            # provider languages so results aren't empty when a client (e.g.
            # Stremio) omits the filter.
            langs = [Language.fromietf("en")]
    except Exception:
        return compat_error("invalid language code", 400, "bad-request")
    season = args.get("season_number", type=int)
    episode = args.get("episode_number", type=int)
    media_type = "episode" if season is not None else "movie"
    try:
        result = service.search(imdb, season, episode, langs, media_type)
    except Exception:
        return compat_error("upstream providers unavailable", 503, "upstream")
    # Paginate on the route side. service.search (and its cache) always hold
    # the full result set; per_page/page are applied here so cache entries
    # stay reusable across different pagination requests.
    page = max(1, args.get("page", default=1, type=int) or 1)
    per_page = args.get("per_page", default=50, type=int) or 50
    per_page = min(max(per_page, 1), 100)
    all_entries = result.get("data", [])
    start = (page - 1) * per_page
    end = start + per_page
    sliced = all_entries[start:end]
    total = len(all_entries)
    total_pages = max(1, (total + per_page - 1) // per_page) if per_page > 0 else 1
    return jsonify({
        "total_pages": total_pages,
        "total_count": total,
        "per_page": per_page,
        "page": page,
        "data": sliced,
    })


@compat_bp.route("/download", methods=["POST"])
@compat_auth(require_jwt=True)
def download():
    body = request.get_json(silent=True) or {}
    fid = body.get("file_id")
    if fid is None or fid == "":
        return compat_error("file_id required", 400, "bad-request")
    try:
        fid_int = int(fid)
    except (TypeError, ValueError):
        return compat_error("file_id must be an integer", 400, "bad-request")
    try:
        # Prefer an absolute URL built from forwarded/host headers. If the
        # inferred host is the internal supervisor loopback (127.x), fall back
        # to a relative path so the client prepends the address it actually
        # connected to rather than its own loopback.
        scheme, host = _infer_client_base(request)
        base_host = f"{scheme}://{host}" if host else ""
        resp = service.download(fid_int, base_host=base_host)
    except FileNotFoundError:
        return compat_error("subtitle not found", 404, "not_found")
    return jsonify(resp)


@compat_bp.route("/download/stream/<stream_token>", methods=["GET"])
@compat_auth(require_jwt=False)
def download_stream(stream_token):
    import logging
    _log = logging.getLogger("bazarr.compat.routes")
    try:
        blob, ctype = service.serve_subtitle_content(stream_token)
    except ValueError:
        return compat_error("stream token expired", 410, "not_found")
    except FileNotFoundError:
        return compat_error("subtitle not found", 404, "not_found")
    except Exception as e:
        _log.exception("compat stream: unexpected: %s", e)
        return compat_error("provider fetch failed", 503, "upstream")
    return Response(blob, mimetype=ctype)


@compat_bp.route("/infos/user", methods=["GET"])
@compat_auth(require_jwt=False)
def infos_user():
    """Api-Key alone is sufficient. OS-compat clients (Jellyfin) poll /infos/user
    for remaining-downloads updates without re-minting the JWT each time."""
    return jsonify(M.user_info_response())


@compat_bp.route("/infos/languages", methods=["GET"])
def infos_languages():
    return jsonify(M.languages_response())


@compat_bp.route("/utilities/guessit", methods=["POST"])
@compat_auth(require_jwt=False)
def utilities_guessit():
    body = request.get_json(silent=True) or {}
    filename = body.get("filename") or request.args.get("filename") or ""
    try:
        return jsonify(service.guessit_filename(filename))
    except ValueError:
        return compat_error("bad filename", 400, "bad-request")
