from unittest.mock import MagicMock
from babelfish import Language
from bazarr.compat import response_mapper as M


def make_sub():
    s = MagicMock(
        provider_name="opensubtitlescom", id="12345",
        language=Language("eng"),
        release_info="Movie.2020.1080p.BluRay.x264-GROUP",
        download_count=500, hearing_impaired=False,
        uploader="Anon", matches={"hash", "release_group"},
    )
    return s


def test_subtitle_entry_has_all_fields_jellyfin_reads():
    entry = M.subtitle_to_os_entry(make_sub(), 42, "episode", "tt12345", 1, 2)
    a = entry["attributes"]
    # Jellyfin requires these exact field names and types
    for k in ("language", "release", "download_count", "ratings", "from_trusted",
              "hearing_impaired", "uploader", "feature_details", "files"):
        assert k in a, f"{k} missing"
    assert a["feature_details"]["feature_type"] in ("Movie", "Episode")  # B12
    # OS.com wire contract: file_id is int, entry-level id is numeric string
    assert isinstance(a["files"][0]["file_id"], int)
    assert a["files"][0]["file_id"] == 42
    assert entry["id"] == "42"
    assert entry["type"] == "subtitle"


def test_feature_type_capitalized_literal():
    e_ep = M.subtitle_to_os_entry(make_sub(), 1, "episode", "tt1", 1, 2)
    assert e_ep["attributes"]["feature_details"]["feature_type"] == "Episode"
    e_mv = M.subtitle_to_os_entry(make_sub(), 1, "movie", "tt1", None, None)
    assert e_mv["attributes"]["feature_details"]["feature_type"] == "Movie"


def test_search_envelope_has_os_com_fields():
    """OS.com search responses expose total_pages, total_count, per_page,
    page at the top level. VLSub reads total_count; Jellyfin reads per_page."""
    entries = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    env = M.search_envelope(entries, per_page=50)
    assert env["data"] == entries
    assert env["total_count"] == 3
    assert env["per_page"] == 50
    assert env["page"] == 1
    assert env["total_pages"] == 1


def test_search_envelope_paginates_total_pages():
    entries = [{"id": str(i)} for i in range(125)]
    env = M.search_envelope(entries, per_page=50)
    assert env["total_count"] == 125
    assert env["total_pages"] == 3


def test_download_response_emits_both_remaining_fields():
    r = M.download_response("https://example/link", reset_iso="2099-01-01T00:00:00Z")
    assert r["remaining"] > 0  # VLSub
    assert r["remaining_downloads"] > 0  # Jellyfin (B11)
    assert r["link"] == "https://example/link"
    assert r["reset_time_utc"] == "2099-01-01T00:00:00Z"


def test_user_info_stub():
    r = M.user_info_response()
    assert r["data"]["remaining_downloads"] > 0
    assert r["data"]["allowed_downloads"] > 0


def test_feature_details_imdb_id_is_int():
    """OS.com wire contract: feature_details.imdb_id is int, not string.
    Accepts 'tt0111161', '0111161', and bare int forms from callers."""
    for imdb in ("tt0111161", "0111161", "111161", 111161):
        e = M.subtitle_to_os_entry(make_sub(), 1, "movie", imdb, None, None)
        assert e["attributes"]["feature_details"]["imdb_id"] == 111161
        assert isinstance(e["attributes"]["feature_details"]["imdb_id"], int)


def test_feature_details_populates_from_video_movie():
    """Movie: title from video.title, movie_name as 'YYYY - Title'."""
    from unittest.mock import MagicMock
    video = MagicMock(title="The Shawshank Redemption", year=1994)
    e = M.subtitle_to_os_entry(make_sub(), 1, "movie", "tt111161", None, None,
                                video=video)
    fd = e["attributes"]["feature_details"]
    assert fd["title"] == "The Shawshank Redemption"
    assert fd["year"] == 1994
    assert fd["movie_name"] == "1994 - The Shawshank Redemption"


def test_feature_details_populates_from_video_episode():
    """Episode: title is the series name, movie_name is the episode title."""
    from unittest.mock import MagicMock
    # Episode video has .series (show name) and .title (episode title)
    video = MagicMock(series="Game of Thrones", title="Winter Is Coming", year=2011)
    e = M.subtitle_to_os_entry(make_sub(), 1, "episode", "tt0944947", 1, 1,
                                video=video)
    fd = e["attributes"]["feature_details"]
    assert fd["feature_type"] == "Episode"
    assert fd["title"] == "Game of Thrones"
    assert fd["movie_name"] == "Winter Is Coming"
    assert fd["season_number"] == 1
    assert fd["episode_number"] == 1
    assert fd["year"] == 2011


def test_feature_details_graceful_without_video():
    """No video threaded through -> empty strings / 0, never throws."""
    e = M.subtitle_to_os_entry(make_sub(), 1, "movie", "tt1", None, None)
    fd = e["attributes"]["feature_details"]
    assert fd["title"] == ""
    assert fd["movie_name"] == ""
    assert fd["year"] == 0
