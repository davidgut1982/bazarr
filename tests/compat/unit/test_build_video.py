"""Tests for the compat _build_video enrichment path.

The compat endpoint has no real video file - it builds a virtual Video from
whatever the client and local library can provide. Providers score heavily on
fields like source, release_group, resolution, so enriching the Video makes
the difference between 0 and dozens of useful results.
"""
from unittest.mock import patch
import pytest


@pytest.fixture(autouse=True)
def _no_library(monkeypatch):
    """Force the library metadata lookup to return empty by default; tests
    that care about it patch the function explicitly."""
    from bazarr.compat import service
    monkeypatch.setattr(service, "_lookup_library_metadata",
                        lambda imdb_id, media_type: {})


def test_movie_without_query_is_bare_but_has_imdb_id():
    from bazarr.compat.service import _build_video
    from subliminal.video import Movie
    v = _build_video("tt0111161", None, None, "movie")
    assert isinstance(v, Movie)
    assert v.imdb_id == "tt0111161"
    assert v.source is None
    assert v.release_group is None


def test_movie_with_filename_extracts_release_metadata():
    """guessit should populate source/release_group/resolution/codec."""
    from bazarr.compat.service import _build_video
    v = _build_video(
        "tt0111161", None, None, "movie",
        query="The.Shawshank.Redemption.1994.1080p.BluRay.x264-RARBG.mkv",
    )
    assert v.resolution == "1080p"
    assert v.source in ("Blu-ray", "BluRay")
    assert v.release_group == "RARBG"
    assert v.video_codec in ("H.264", "h264", "x264")
    # guessit should recover the year even when the library lookup is empty
    assert v.year == 1994


def test_movie_uses_library_title_when_available():
    from bazarr.compat import service
    from bazarr.compat.service import _build_video
    with patch.object(service, "_lookup_library_metadata",
                       return_value={"title": "The Shawshank Redemption", "year": "1994"}):
        v = _build_video("tt0111161", None, None, "movie")
    assert v.title == "The Shawshank Redemption"
    assert v.year == 1994


def test_episode_sets_series_imdb_and_season_episode():
    from bazarr.compat.service import _build_video
    from subliminal.video import Episode
    v = _build_video("tt0903747", 1, 2, "episode",
                     query="Breaking.Bad.S01E02.720p.HDTV.x264-GROUP.mkv")
    assert isinstance(v, Episode)
    assert v.series_imdb_id == "tt0903747"
    assert v.season == 1 and v.episode == 2
    assert v.resolution == "720p"
    assert v.release_group == "GROUP"


def test_moviehash_is_wired_for_opensubtitles_providers():
    """OS-style moviehash enables exact-hash matching on the OS providers."""
    from bazarr.compat.service import _build_video
    v = _build_video("tt0111161", None, None, "movie",
                     moviehash="8e245d9679d31e12")
    assert v.hashes.get("opensubtitles") == "8e245d9679d31e12"
    assert v.hashes.get("opensubtitlescom") == "8e245d9679d31e12"


def test_library_title_wins_over_guessit_title_but_guessit_fills_gaps():
    """When both sources have info, library title wins (curated); guessit
    provides the release-quality fields library lookup can't supply."""
    from bazarr.compat import service
    from bazarr.compat.service import _build_video
    with patch.object(service, "_lookup_library_metadata",
                       return_value={"title": "The Shawshank Redemption", "year": "1994"}):
        v = _build_video(
            "tt0111161", None, None, "movie",
            query="shawshank.1994.2160p.UHD.BluRay.x265-TERMiNAL.mkv",
        )
    assert v.title == "The Shawshank Redemption"  # library beats guessit
    assert v.resolution == "2160p"  # guessit still fills release quality
    assert v.release_group == "TERMiNAL"
