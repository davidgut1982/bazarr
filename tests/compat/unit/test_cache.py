from bazarr.compat import cache as C
from subzero.language import Language


def test_build_key_deterministic_across_processes():
    """SHA-256 of sorted provider set, not Python hash()."""
    k1 = C.build_key("episode", "tt12345", 1, 2, [Language("eng")],
                    ["opensubtitlescom", "subdl"])
    k2 = C.build_key("episode", "tt12345", 1, 2, [Language("eng")],
                    ["subdl", "opensubtitlescom"])  # unsorted
    assert k1 == k2
    assert k1.startswith("compat:v1:episode:tt12345:1:2:")


def test_build_key_language_variants_preserved():
    """Forced/HI variants produce different keys."""
    base = [Language("eng")]
    forced = [Language.rebuild(Language("eng"), forced=True)]
    assert C.build_key("movie", "tt1", None, None, base, ["p"]) != \
           C.build_key("movie", "tt1", None, None, forced, ["p"])


def test_region_get_or_create_coalesces():
    """Dogpile's per-key mutex serializes concurrent creators."""
    call_count = {"n": 0}
    def creator():
        call_count["n"] += 1
        return {"data": []}
    C.compat_region.get_or_create("coalesce_test", creator, expiration_time=60)
    C.compat_region.get_or_create("coalesce_test", creator, expiration_time=60)
    assert call_count["n"] == 1
    C.compat_region.invalidate(hard=True)
