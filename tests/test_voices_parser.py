from __future__ import annotations

from archive.models import EntityRole, SourceItem
from archive.derived import derive_entity_claims
from archive.voices import parse_voices_interviewee_label, strip_media_extensions


def test_repeated_media_extensions_are_removed() -> None:
    assert strip_media_extensions("V1004 Lei Hennessy.mov.mp4") == "V1004 Lei Hennessy"
    assert strip_media_extensions("Jane Doe.MOV.MP4") == "Jane Doe"


def test_vcode_filename_is_high_confidence() -> None:
    parsed = parse_voices_interviewee_label("V1004 Lei Hennessy.mov.mp4")
    assert parsed is not None
    assert parsed.name_raw == "Lei Hennessy"
    assert parsed.normalized_name == "Lei Hennessy"
    assert parsed.confidence == 0.95
    assert parsed.method == "voices_911_vcode_filename_convention"


def test_separate_trailing_w_marker_is_removed_conservatively() -> None:
    parsed = parse_voices_interviewee_label("David Shaman W.mov.mp4")
    assert parsed is not None
    assert parsed.name_raw == "David Shaman"
    assert parsed.normalized_name == "David Shaman"
    assert parsed.confidence == 0.88
    assert parsed.method == "voices_911_trailing_w_filename_convention"


def test_attached_suffixes_are_preserved_not_guessed_away() -> None:
    attached_w = parse_voices_interviewee_label("Jian Hong HuangW.mov.mp4")
    numeric = parse_voices_interviewee_label("Nathan Farb2.mov.mp4")

    assert attached_w is not None and attached_w.name_raw == "Jian Hong HuangW"
    assert attached_w.normalized_name is None
    assert attached_w.confidence == 0.70
    assert numeric is not None and numeric.name_raw == "Nathan Farb2"
    assert numeric.normalized_name is None
    assert numeric.confidence == 0.70


def test_entity_derivation_accepts_string_collection_id() -> None:
    item = SourceItem(
        id="voice:1",
        source_id="september-11-digital-archive",
        source_item_id="1",
        source_url="https://911digitalarchive.org/items/show/1",
        title_raw="Efrain Huaman Carrion W.mov.mp4",
        metadata_raw={"collection_id": "267"},
    )

    claims = derive_entity_claims([item])
    assert len(claims) == 1
    assert claims[0].role == EntityRole.INTERVIEWEE
    assert claims[0].name_raw == "Efrain Huaman Carrion"
    assert claims[0].confidence == 0.88
