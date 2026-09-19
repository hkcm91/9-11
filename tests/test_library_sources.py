import io
import json
from pathlib import Path

import pytest

from archive.document_library import DocumentLibrary, digest
from archive.library_sources import DownloadLimit, bulk_ingest, pentagon_manifest, preserve_stream


def test_nara_catalog_preserves_identifiers_and_titles():
    html = '''<table><tr><td><a href="https://nara-media-001.s3.amazonaws.com/a.pdf">Part I &amp; Index</a></td>
        <td>(2.5 MB)</td><td><a href="https://catalog.archives.gov/id/123">123</a></td></tr></table>'''
    entry = pentagon_manifest(html)[0]
    assert entry["title"] == "Pentagon Papers — Part I & Index"
    assert entry["source_item_id"] == "123"
    assert entry["advertised_bytes"] == 2_500_000
    with pytest.raises(ValueError, match="origin"):
        pentagon_manifest(html.replace("nara-media-001.s3.amazonaws.com", "untrusted.example"))
    with pytest.raises(ValueError, match="No Pentagon"):
        pentagon_manifest("<p>No inventory</p>")


def test_streaming_limits_integrity_and_cleanup(tmp_path):
    with pytest.raises(DownloadLimit):
        preserve_stream(io.BytesIO(b"123456"), tmp_path, 5)
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError, match="Incomplete"):
        preserve_stream(io.BytesIO(b"123"), tmp_path, 10, expected_bytes=5)
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError, match="checksum"):
        preserve_stream(io.BytesIO(b"123"), tmp_path, 10, "wrong")
    assert not list(tmp_path.iterdir())
    path, count = preserve_stream(io.BytesIO(b"123"), tmp_path, 10)
    assert count == 3 and path.name == digest(b"123")
    assert preserve_stream(io.BytesIO(b"123"), tmp_path, 10)[0] == path
    assert len(list(tmp_path.iterdir())) == 1


def test_bulk_resume_inventory_and_limits(tmp_path):
    lib = DocumentLibrary(tmp_path / "library.sqlite", tmp_path / "objects")
    try:
        entries = []
        for number in range(3):
            source = tmp_path / f"{number}.txt"
            source.write_text("public text " + str(number))
            entries.append(dict(collection="pentagon_papers", release_id="test", source_item_id=str(number),
                title=f"Volume {number}", format="text", path=source.name, source_url=f"https://example.org/{number}"))
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps(entries))
        result = bulk_ingest(lib, manifest, max_total_bytes=14)
        assert result["results"][0]["status"] == "processed"
        assert result["results"][1]["status"] == "deferred"
        assert lib.inventory_coverage()[0]["pending"] == 2
        # A completed version can resume without the source being reachable.
        (tmp_path / "0.txt").unlink()
        result = bulk_ingest(lib, manifest)
        assert result["results"][0]["resumed"]
        assert all(row["status"] == "processed" for row in result["results"])
        assert lib.inventory_coverage()[0] == dict(collection="pentagon_papers", release_id="test", discovered=3, processed=3, failed=0, pending=0, published=0)
        assert lib.db.execute("SELECT count(*) FROM library_documents").fetchone()[0] == 3
    finally:
        lib.close()


def test_parse_failure_reuses_preserved_download(tmp_path, monkeypatch):
    lib = DocumentLibrary(tmp_path / "library.sqlite", tmp_path / "objects")
    source = tmp_path / "source.txt"
    source.write_text("Public document")
    entry = dict(collection="pentagon_papers", release_id="test", source_item_id="one",
        title="Volume", format="text", path=source.name, source_url="https://example.org/one")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([entry]))
    original = lib.ingest_preserved
    try:
        def fail(*args):
            raise ValueError("Parser unavailable")
        monkeypatch.setattr(lib, "ingest_preserved", fail)
        assert bulk_ingest(lib, manifest)["results"][0]["status"] == "failed"
        downloaded_at = lib.db.execute("SELECT downloaded_at FROM library_downloads").fetchone()[0]
        source.unlink()
        monkeypatch.setattr(lib, "ingest_preserved", original)
        result = bulk_ingest(lib, manifest)
        assert result["bytes_transferred"] == 0
        assert result["results"][0]["status"] == "processed"
        assert lib.db.execute("SELECT retrieved_at FROM library_documents").fetchone()[0] == downloaded_at
    finally:
        lib.close()


def test_inventory_atomic_validation(tmp_path):
    lib = DocumentLibrary(tmp_path / "library.sqlite", tmp_path / "objects")
    try:
        with pytest.raises(ValueError):
            lib.register_inventory([{}])
        assert lib.inventory_coverage() == []
        manifest = Path(__file__).parents[1] / "examples/library/pentagon-papers.json"
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        assert len(entries) == 49
        lib.register_inventory(entries)
        lib.register_inventory(entries)
        assert lib.inventory_coverage()[0]["discovered"] == 49
        assert lib.inventory_coverage()[0]["pending"] == 49
    finally:
        lib.close()


def test_cablegate_sampler_rejects_text_fragments_and_incomplete_rows(tmp_path, monkeypatch):
    import csv
    from contextlib import contextmanager
    from archive.library_cablegate import valid_cable_row
    from evidence_collections.wikileaks import remote_sources
    fields = remote_sources.CABLEGATE_FIELDS
    good = dict(zip(fields, ["1", "1972-01-01", "72TEHRAN1164", "TEHRAN", "UNCLASSIFIED", "", "", "Public cable text"]))
    assert valid_cable_row(good)
    assert not valid_cable_row({**good, "reference": "STRESSING OUR INTEREST"})
    assert not valid_cable_row({**good, "body": None})
    assert not valid_cable_row({**good, None: ["extra field"]})
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=fields)
    writer.writerow({**good, "reference": "FRAGMENT"})
    writer.writerow(good)
    @contextmanager
    def local_stream(*args, **kwargs):
        yield io.StringIO(text.getvalue())
    monkeypatch.setattr(remote_sources, "_remote_csv_text_stream", local_stream)
    result = remote_sources.stream_csv_sample("https://example.org/test.csv", tmp_path / "out.csv",
        limit=1, fieldnames=fields, row_filter=valid_cable_row)
    assert result["records"] == 1
    assert result["skipped_invalid_rows"] == 1


def test_quarantined_version_cannot_be_published(tmp_path):
    lib = DocumentLibrary(tmp_path / "library.sqlite", tmp_path / "objects")
    try:
        entry = dict(collection="wikileaks", release_id="test", source_item_id="one",
            title="Record", format="text", source_url="https://example.org/one")
        identifier = lib.ingest(entry, payload=b"Public source text")
        with lib.db:
            lib.db.execute("UPDATE library_documents SET extraction_status='quarantined' WHERE id=?", (identifier,))
        with pytest.raises(ValueError, match="quarantined"):
            lib.publish(identifier, True, "editor", "Review")
        assert lib.document(identifier) is None
    finally:
        lib.close()


def test_cablegate_refetch_preserves_document_identity(tmp_path, monkeypatch):
    import csv
    from archive import library_cablegate as module
    lib = DocumentLibrary(tmp_path / "library.sqlite", tmp_path / "objects")
    def sample(url, output, **kwargs):
        row = dict(zip(module.CABLEGATE_FIELDS, ["1", "1972-01-01", "72TEHRAN1164", "TEHRAN", "UNCLASSIFIED", "", "", "Public cable text"]))
        assert kwargs["row_filter"](row)
        with Path(output).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=module.CABLEGATE_FIELDS)
            writer.writeheader()
            writer.writerow(row)
        return {"records": 1, "url": url, "skipped_invalid_rows": 0}
    monkeypatch.setattr(module, "discover_cablegate_csv_url", lambda: "https://example.org/cables.csv")
    monkeypatch.setattr(module, "stream_csv_sample", sample)
    try:
        assert module.fetch_cablegate(lib, tmp_path / "sample", 1)["processed"] == 1
        assert module.fetch_cablegate(lib, tmp_path / "sample", 1)["processed"] == 1
        assert lib.db.execute("SELECT count(*) FROM library_documents").fetchone()[0] == 1
        assert lib.search("cable") == []
        assert lib.inventory_coverage()[0]["discovered"] == 1
    finally:
        lib.close()
