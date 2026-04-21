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


@compat_bp.route("/login", methods=["POST"])
@compat_auth(require_jwt=False)
def login():
    return jsonify({
        "token": auth.mint_jwt(),
        "status": 200,
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
    if not langs_s or not imdb:
        return compat_error("languages and (imdb_id|tmdb_id|query) required", 400, "bad-request")
    from babelfish import Language
    try:
        langs = [Language.fromietf(c.strip()) for c in langs_s.split(",") if c.strip()]
    except Exception:
        return compat_error("invalid language code", 400, "bad-request")
    season = args.get("season_number", type=int)
    episode = args.get("episode_number", type=int)
    media_type = "episode" if season is not None else "movie"
    try:
        result = service.search(imdb, season, episode, langs, media_type)
    except Exception:
        return compat_error("upstream providers unavailable", 503, "upstream")
    return jsonify(result)


@compat_bp.route("/download", methods=["POST"])
@compat_auth(require_jwt=True)
def download():
    body = request.get_json(silent=True) or {}
    fid = body.get("file_id")
    if not fid:
        return compat_error("file_id required", 400, "bad-request")
    try:
        resp = service.download(str(fid), base_host=request.host_url.rstrip("/"))
    except FileNotFoundError:
        return compat_error("subtitle not found", 404, "not_found")
    return jsonify(resp)


@compat_bp.route("/download/stream/<stream_token>", methods=["GET"])
@compat_auth(require_jwt=False)
def download_stream(stream_token):
    try:
        blob, ctype = service.serve_subtitle_content(stream_token)
    except ValueError:
        return compat_error("stream token expired", 410, "not_found")
    except FileNotFoundError:
        return compat_error("subtitle not found", 404, "not_found")
    except Exception:
        return compat_error("provider fetch failed", 503, "upstream")
    return Response(blob, mimetype=ctype)


@compat_bp.route("/infos/user", methods=["GET"])
@compat_auth(require_jwt=True)
def infos_user():
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
