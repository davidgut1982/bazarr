import time
from bazarr.compat.file_id_store import FileIdStore, get_store, reset_store


def test_put_returns_monotonic_int():
    s = FileIdStore()
    a = s.put({"p": "x", "i": "1"}, ttl_seconds=60)
    b = s.put({"p": "x", "i": "2"}, ttl_seconds=60)
    assert isinstance(a, int) and isinstance(b, int)
    assert b == a + 1


def test_get_roundtrips_payload():
    s = FileIdStore()
    fid = s.put({"p": "os", "i": "42", "l": "eng"}, ttl_seconds=60)
    ok, payload = s.get(fid)
    assert ok
    assert payload == {"p": "os", "i": "42", "l": "eng"}


def test_get_accepts_string_int():
    s = FileIdStore()
    fid = s.put({"p": "x", "i": "1"}, ttl_seconds=60)
    ok, _ = s.get(str(fid))
    assert ok


def test_get_rejects_unknown_id():
    s = FileIdStore()
    ok, payload = s.get(9999)
    assert not ok and payload == {}


def test_get_rejects_non_numeric():
    s = FileIdStore()
    for bogus in ("abc", None, "", object()):
        ok, _ = s.get(bogus)
        assert not ok


def test_expired_entry_removed_on_access():
    s = FileIdStore()
    fid = s.put({"p": "x", "i": "1"}, ttl_seconds=1)
    time.sleep(1.1)
    ok, _ = s.get(fid)
    assert not ok
    assert len(s) == 0


def test_overflow_triggers_gc():
    """Store keeps at most max_entries (best-effort; evicts expired + oldest)."""
    s = FileIdStore(max_entries=5)
    for _ in range(10):
        s.put({"p": "x", "i": "1"}, ttl_seconds=60)
    assert len(s) <= 5


def test_singleton_survives_reset():
    get_store().put({"p": "x", "i": "1"}, ttl_seconds=60)
    assert len(get_store()) >= 1
    reset_store()
    assert len(get_store()) == 0
