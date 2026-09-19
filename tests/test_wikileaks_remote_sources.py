import io
import json
from pathlib import Path

import py7zr

from evidence_collections.wikileaks.remote_sources import (
    CABLEGATE_FIELDS,
    WAR_DIARY_FIELDS,
    discover_archive_csv_url,
    discover_cablegate_csv_url,
    stream_csv_sample,
)


def test_discover_cablegate_csv_url_prefers_largest_csv(monkeypatch) -> None:
    payload = {
        "files": [
            {"name": "checksums.csv", "size": "1200"},
            {"name": "cables.csv", "size": "1600000000"},
            {"name": "readme.txt", "size": "400"},
        ]
    }

    monkeypatch.setattr(
        "evidence_collections.wikileaks.remote_sources._open",
        lambda url, timeout=30.0: io.BytesIO(json.dumps(payload).encode("utf-8")),
    )

    url = discover_cablegate_csv_url()

    assert url.endswith("/wikileaks-cables-csv/cables.csv")


def test_discover_archive_csv_url_supports_war_diary_item(monkeypatch) -> None:
    payload = {
        "files": [
            {"name": "afg-war-diary.csv.7z", "size": "77000000"},
            {"name": "metadata.xml", "size": "1000"},
        ]
    }

    monkeypatch.setattr(
        "evidence_collections.wikileaks.remote_sources._open",
        lambda url, timeout=30.0: io.BytesIO(json.dumps(payload).encode("utf-8")),
    )

    url = discover_archive_csv_url("WikileaksWarDiaryCsv")

    assert url.endswith("/WikileaksWarDiaryCsv/afg-war-diary.csv.7z")


def test_stream_headered_csv_sample_writes_only_requested_records(tmp_path: Path, monkeypatch) -> None:
    body = (
        "id,title,summary\n"
        "1,First,Alpha\n"
        "2,Second,Beta\n"
        "3,Third,Gamma\n"
    ).encode("utf-8")

    monkeypatch.setattr(
        "evidence_collections.wikileaks.remote_sources._open",
        lambda url, timeout=60.0: io.BytesIO(body),
    )

    output = tmp_path / "sample.csv"
    result = stream_csv_sample(
        "https://example.test/data.csv",
        output,
        limit=2,
    )

    assert result["records"] == 2
    assert result["remote_headerless"] is False
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert "Third" not in output.read_text(encoding="utf-8")


def test_stream_headerless_cablegate_assigns_known_schema(tmp_path: Path, monkeypatch) -> None:
    body = (
        '1,"12/28/1966 18:48",66BUENOSAIRES2481,"Embassy Buenos Aires",UNCLASSIFIED,66STATE106206,"P R HEADER","Cable body one"\n'
        '2,"01/02/1967 09:00",67STATE000002,"Secretary of State",CONFIDENTIAL,66BUENOSAIRES2481,"P R HEADER 2","Cable body two"\n'
    ).encode("utf-8")

    monkeypatch.setattr(
        "evidence_collections.wikileaks.remote_sources._open",
        lambda url, timeout=60.0: io.BytesIO(body),
    )

    output = tmp_path / "plusd.csv"
    result = stream_csv_sample(
        "https://example.test/cables.csv",
        output,
        limit=2,
        fieldnames=CABLEGATE_FIELDS,
    )

    assert result["remote_headerless"] is True
    assert result["columns"] == CABLEGATE_FIELDS

    text = output.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("row_id,date,reference,origin")
    assert "66BUENOSAIRES2481" in text


def test_war_diary_schema_contains_adapter_fields() -> None:
    assert WAR_DIARY_FIELDS[0] == "ReportKey"
    assert "DateOccurred" in WAR_DIARY_FIELDS
    assert "TrackingNumber" in WAR_DIARY_FIELDS
    assert "Summary" in WAR_DIARY_FIELDS
    assert "MGRS" in WAR_DIARY_FIELDS
    assert "Classification" in WAR_DIARY_FIELDS



def test_stream_7z_headerless_csv_sample(tmp_path: Path, monkeypatch) -> None:
    source_csv = tmp_path / "afg-war-diary.csv"
    source_csv.write_text(
        "report-1,2004-01-01 00:00:00,Enemy Action,direct fire,track-1,title one,summary one,RC EAST,ENEMY,False,UNIT,UNIT,Infantry,0,0,0,0,0,0,0,0,0,42SWB3900916257,32.6,69.4,UNKNOWN,UNKNOWN,,,ENEMY,RED,SECRET\n"
        "report-2,2004-01-01 01:00:00,Friendly Action,cache found/cleared,track-2,title two,summary two,RC EAST,FRIEND,False,UNIT,UNIT,Infantry,0,0,0,0,0,0,0,0,0,42SWB3900916258,32.7,69.5,UNKNOWN,UNKNOWN,,,FRIEND,BLUE,SECRET\n",
        encoding="utf-8",
    )
    archive_path = tmp_path / "afg-war-diary.csv.7z"
    with py7zr.SevenZipFile(archive_path, "w") as archive:
        archive.write(source_csv, arcname="afg-war-diary.csv")
    archive_bytes = archive_path.read_bytes()

    monkeypatch.setattr(
        "evidence_collections.wikileaks.remote_sources._open",
        lambda url, timeout=60.0: io.BytesIO(archive_bytes),
    )

    output = tmp_path / "war-diaries.csv"
    result = stream_csv_sample(
        "https://example.test/afg-war-diary.csv.7z",
        output,
        limit=1,
        fieldnames=WAR_DIARY_FIELDS,
    )

    assert result["records"] == 1
    text = output.read_text(encoding="utf-8")
    assert "ReportKey,DateOccurred" in text
    assert "report-1" in text
    assert "report-2" not in text
