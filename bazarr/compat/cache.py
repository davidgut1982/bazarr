from __future__ import annotations
import hashlib
import json
from dogpile.cache import make_region

compat_region = make_region(key_mangler=lambda k: k).configure(
    "dogpile.cache.memory",
    arguments={},
)


def build_key(media_type: str, imdb_id: str, season: int | None,
              episode: int | None, languages, enabled_providers) -> str:
    """Deterministic across restarts. Language variants preserved."""
    lang_tuples = sorted(
        (str(l.alpha3), str(l.country) if l.country else "",
         bool(getattr(l, "forced", False)), bool(getattr(l, "hi", False)))
        for l in languages
    )
    provider_hash = hashlib.sha256(
        ",".join(sorted(enabled_providers)).encode()
    ).hexdigest()[:16]
    return (
        f"compat:v1:{media_type}:{imdb_id}:{season or 0}:{episode or 0}"
        f":{provider_hash}:{json.dumps(lang_tuples, sort_keys=True, separators=(',', ':'))}"
    )


def invalidate_all() -> None:
    """Hard invalidation of the entire compat region. Called post secret rotation."""
    compat_region.invalidate(hard=True)
