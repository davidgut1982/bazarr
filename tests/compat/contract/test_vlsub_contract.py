import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from babelfish import Language
from compat import service, cache as C


def _resolve(obj, path):
    """Simple JSONPath subset: data[0].attributes.files[0].file_id"""
    parts = path.replace("[", ".[").split(".")
    for p in parts:
        if not p:
            continue
        if p.startswith("["):
            obj = obj[int(p[1:-1])]
        else:
            obj = obj[p]
    return obj


def _check_type(value, type_name: str) -> bool:
    if type_name == "str":
        return isinstance(value, str)
    if type_name == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "bool":
        return isinstance(value, bool)
    return True


def test_vlsub_contract(monkeypatch):
    """Every JSON path VLSub reads from a subtitle search response must resolve
    with the correct primitive type. Extracted from the VLSub audit report."""
    monkeypatch.setattr("compat.auth.settings.compat_endpoint.file_id_secret", "f" * 32)
    contract_file = Path(__file__).parent.parent / "fixtures" / "client_contracts" / "vlsub_required.json"
    contract = json.loads(contract_file.read_text())
    C.invalidate_all()

    fake_sub = MagicMock(
        provider_name="opensubtitlescom", id="99",
        language=Language("eng"),
        release_info="Movie.2020.1080p",
        download_count=100, hearing_impaired=False,
        ratings=0, uploader="Anon", upload_date=None,
    )

    with patch("compat.service._get_compat_pool") as gp, \
         patch("compat.service.list_all_subtitles_parallel") as lf, \
         patch("compat.service.auth.mint_file_id", return_value=42):
        lf.return_value = {MagicMock(): [fake_sub]}
        gp.return_value.providers = ["opensubtitlescom"]
        gp.return_value.discarded_providers = set()
        resp = service.search("tt1", 1, 2, [Language("eng")], "episode")

    for path, expected_type in contract.items():
        value = _resolve(resp, path)
        assert value is not None, f"VLSub requires {path}"
        assert _check_type(value, expected_type), (
            f"VLSub requires {path} as {expected_type}, got {type(value).__name__}"
        )

    # B12 exact capitalization (server contract, not just JSONPath resolution)
    assert resp["data"][0]["attributes"]["feature_details"]["feature_type"] == "Episode"
    C.invalidate_all()
