from __future__ import annotations
import datetime as dt

_STUB_REMAINING = 1000


def _tomorrow_utc_iso() -> str:
    t = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def subtitle_to_os_entry(sub, file_id: str, media_type: str, imdb_id: str,
                         season=None, episode=None) -> dict:
    """Map a Subtitle instance to an OS.com `data[].attributes` shape.

    Field set = union of what VLSub/Stremio/Kodi/Jellyfin parse. Unknown fields
    get safe defaults.
    """
    lang = getattr(sub, "language", None)
    lang_alpha2 = getattr(lang, "alpha2", None) or ""
    release = getattr(sub, "release_info", "") or ""
    uploader_name = getattr(sub, "uploader", None) or getattr(sub, "provider_name", "")
    feat_type = "Episode" if media_type == "episode" else "Movie"  # B12
    attributes = {
        "language": str(lang_alpha2).lower(),
        "subtitle_id": str(getattr(sub, "id", "")),
        "release": release,
        "download_count": int(getattr(sub, "download_count", 0) or 0),
        "ratings": float(getattr(sub, "ratings", 0) or 0),
        "votes": 0,
        "from_trusted": bool(getattr(sub, "from_trusted", False)),
        "hd": bool(getattr(sub, "hd", False)),
        "hearing_impaired": bool(getattr(sub, "hearing_impaired", False)),
        "moviehash_match": False,
        "ai_translated": False,
        "machine_translated": False,
        "foreign_parts_only": False,
        "fps": 0.0,
        "upload_date": getattr(sub, "upload_date", None).isoformat() + "Z"
                       if getattr(sub, "upload_date", None) else "",
        "uploader": {"name": str(uploader_name)},
        "feature_details": {
            "feature_type": feat_type,
            "imdb_id": imdb_id,
            "season_number": int(season) if season is not None else 0,
            "episode_number": int(episode) if episode is not None else 0,
            "title": "",
            "movie_name": "",
            "year": 0,
        },
        "files": [{
            "file_id": file_id,
            "file_name": f"{imdb_id}.{lang_alpha2}.srt",
        }],
    }
    return {"id": file_id, "type": "subtitle", "attributes": attributes}


def download_response(link: str, reset_iso: str | None = None) -> dict:
    return {
        "link": link,
        "remaining": _STUB_REMAINING,
        "remaining_downloads": _STUB_REMAINING,  # B11 — Jellyfin
        "requests": 0,
        "reset_time": reset_iso or _tomorrow_utc_iso(),
        "reset_time_utc": reset_iso or _tomorrow_utc_iso(),
    }


def user_info_response() -> dict:
    return {
        "data": {
            "allowed_downloads": _STUB_REMAINING,
            "remaining_downloads": _STUB_REMAINING,
            "remaining": _STUB_REMAINING,
            "reset_time_utc": _tomorrow_utc_iso(),
            "level": "User",
            "user_id": 0,
            "ext_installed": False,
            "vip": False,
        }
    }


def languages_response() -> dict:
    """Lowercase BCP-47 per I10; comprehensive for all audited clients."""
    codes = [
        "en", "es", "fr", "de", "it", "pt-br", "pt-pt", "nl", "pl",
        "ru", "zh-cn", "zh-tw", "ja", "ko", "ar", "hu", "tr", "cs",
        "da", "no", "sv", "fi", "el", "he", "th", "vi", "ro", "sk",
        "bg", "uk", "hr", "sr", "id",
    ]
    return {"data": [{"code": c, "name": c.upper()} for c in codes]}
