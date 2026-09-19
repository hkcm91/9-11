import io
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from archive.document_library import DocumentLibrary, digest, extract_pages
from archive.library_cli import handler_for, main
from historical_engine.ai.fakes import FakeDecisionProvider


@pytest.fixture
def library(tmp_path):
    value = DocumentLibrary(tmp_path / "archive.sqlite", tmp_path / "objects")
    yield value
    value.close()


def entry(tmp_path, text="Public evidence\fSecond page about a diplomatic cable", **overrides):
    path = tmp_path / "source.txt"
    path.write_text(text, encoding="utf-8")
    return dict(collection="wikileaks", release_id="pilot", source_item_id="cable-1",
                source_url="https://example.org/cable-1", title="A diplomatic record",
                format="text", path=str(path), **overrides)


def approve(library, identifier):
    library.publish(identifier, True, "test-editor", "Reviewed for pilot publication")


def test_versions_deduplication_and_provenance(library, tmp_path):
    item = entry(tmp_path)
    first = library.ingest(item)
    assert library.ingest(item) == first
    changed = library.ingest(entry(tmp_path, text="Corrected source edition"))
    assert changed != first
    assert library.db.execute("SELECT count(*) FROM source_records").fetchone()[0] == 1
    assert library.db.execute("SELECT count(*) FROM source_observations").fetchone()[0] == 2
    assert library.db.execute("SELECT text FROM library_pages WHERE document_id=? AND number=1", (first,)).fetchone()[0] == "Public evidence"
    assert len(list(library.objects.iterdir())) == 2


def test_publication_gate_search_citations_and_withdrawal(library, tmp_path):
    identifier = library.ingest(entry(tmp_path))
    assert not library.search("diplomatic")
    assert library.document(identifier) is None
    approve(library, identifier)
    result = library.search('cable OR " * -')
    assert result == []  # User input is literal AND terms, not executable FTS syntax.
    result = library.search("cable", "wikileaks")
    assert len(result) == 1 and result[0]["page"] == 2
    assert result[0]["id"] == identifier
    assert not library.search("cable", "snowden")
    assert library.document(identifier)["pages"][1]["text"].startswith("Second page")
    library.publish(identifier, False, "editor", "Withdraw pending source correction")
    assert not library.search("cable")
    assert library.document(identifier) is None
    assert library.coverage(public_only=True) == []


def test_manifest_failures_retry_and_coverage(library, tmp_path):
    good = entry(tmp_path)
    bad = {**good, "source_item_id": "missing", "path": "missing.txt"}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([bad, good]), encoding="utf-8")
    result = library.ingest_manifest(manifest)
    assert [r["status"] for r in result] == ["failed", "processed"]
    assert library.coverage()[0] == dict(collection="wikileaks", release_id="pilot", inventoried=2, failed=1, processed=1)
    (tmp_path / "missing.txt").write_text("Recovered public document")
    library.ingest_manifest(manifest)
    assert library.coverage()[0]["failed"] == 0
    assert library.coverage()[0]["inventoried"] == 2
    assert library.db.execute("SELECT count(*) FROM library_documents").fetchone()[0] == 2


def test_checksum_and_object_integrity(library, tmp_path):
    item = entry(tmp_path, sha256="wrong")
    with pytest.raises(ValueError, match="checksum"):
        library.ingest(item)
    item.pop("sha256")
    identifier = library.ingest(item)
    sha = library.db.execute("SELECT sha256 FROM library_documents WHERE id=?", (identifier,)).fetchone()[0]
    (library.objects / sha).write_bytes(b"corruption")
    with pytest.raises(ValueError, match="integrity"):
        library.ingest({**item, "title": "Alternate metadata"})


def test_blank_pdf_and_missing_ocr(library, tmp_path):
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)
    assert extract_pages(buffer.getvalue(), "pdf")[0] == [""]
    item = entry(tmp_path)
    path = tmp_path / "scan.pdf"
    path.write_bytes(buffer.getvalue())
    identifier = library.ingest({**item, "path": str(path), "format": "pdf"})
    approve(library, identifier)
    assert library.document(identifier)["extraction_status"] == "needs_ocr"
    with pytest.raises(ValueError, match="OCR"):
        library.compare(identifier, 1, identifier, 1, "same_event", FakeDecisionProvider())


def test_jev_proposal_only_cache_and_access_gate(library, tmp_path):
    identifier = library.ingest(entry(tmp_path))
    provider = FakeDecisionProvider()
    with pytest.raises(ValueError, match="approved"):
        library.compare(identifier, 1, identifier, 2, "same_event", provider)
    assert not provider.calls
    approve(library, identifier)
    record = library.document(identifier)["record_id"]
    provider.script("same_event", record, "same", .95, object_id=record)
    result = library.compare(identifier, 1, identifier, 2, "same_event", provider)
    assert result["review_status"] == "proposed"
    assert result["passages"][1]["page"] == 2
    assert library.compare(identifier, 1, identifier, 2, "same_event", provider) == result
    assert len(provider.calls) == 1
    assert library.db.execute("SELECT review_status FROM agent_proposals").fetchone()[0] == "proposed"
    library.publish(identifier, False, "editor", "Withdraw")
    with pytest.raises(ValueError):
        library.compare(identifier, 1, identifier, 2, "same_event", provider)


def test_http_reader_original_and_hidden_document(library, tmp_path):
    identifier = library.ingest(entry(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(library.store.path, library.objects))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base) as response:
            assert b"Public Record" in response.read()
        for suffix in ("", "/original"):
            with pytest.raises(HTTPError) as error:
                urlopen(base + "/api/documents/" + identifier + suffix)
            assert error.value.code == 404
        approve(library, identifier)
        with urlopen(base + "/api/documents/" + identifier) as response:
            metadata = json.load(response)
            assert metadata["page_count"] == 2
            assert "pages" not in metadata
        with urlopen(base + "/api/documents/" + identifier + "/pages/2") as response:
            assert json.load(response)["text"].startswith("Second page")
        with urlopen(base + "/api/documents/" + identifier + "/original") as response:
            assert response.headers["Content-Disposition"].startswith("attachment")
            assert digest(response.read()) == library.document(identifier)["sha256"]
        with urlopen(base + "/api/search?q=cable") as response:
            assert json.load(response)[0]["page"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_cli_failure_exit_code(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text('[{}]')
    assert main(["--database", str(tmp_path / "library.sqlite"), "--objects", str(tmp_path / "objects"), "ingest", str(path)]) == 1
    assert json.loads(capsys.readouterr().out)[0]["status"] == "failed"


def test_original_page_image_respects_publication_and_page_bounds(library, tmp_path):
    import pymupdf
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((40, 40), "Original contents")
        payload = pdf.tobytes()
    identifier = library.ingest({**entry(tmp_path), "format": "pdf"}, payload=payload)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(library.store.path, library.objects))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/api/documents/{identifier}/pages/"
    try:
        with pytest.raises(HTTPError) as error:
            urlopen(base + "1/image")
        assert error.value.code == 404
        approve(library, identifier)
        with urlopen(base + "1/image") as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read().startswith(b"\x89PNG\r\n\x1a\n")
        with pytest.raises(HTTPError) as error:
            urlopen(base + "2/image")
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_existing_wikileaks_record_bridge(library, tmp_path):
    from pathlib import Path
    source = Path(__file__).parents[1] / "src/evidence_collections/wikileaks/fixtures/real_sample.jsonl"
    rows = library.import_records(source, "wikileaks", "regression-metadata-sample")
    assert len(rows) == 2 and all(row["status"] == "processed" for row in rows)
    first = rows[0]["document_id"]
    approve(library, first)
    doc = library.document(first)
    assert "may be metadata only" in doc["pages"][0]["text"]
    assert "Title: EGYPT" in doc["pages"][0]["text"]
    assert (library.objects / doc["sha256"]).read_bytes() == source.read_bytes().splitlines(keepends=True)[0]
    assert library.import_records(source, "wikileaks", "regression-metadata-sample")[0]["document_id"] == first
    assert library.coverage()[0]["inventoried"] == 2


def test_jev_rejects_unsupplied_evidence(library, tmp_path):
    identifier = library.ingest(entry(tmp_path))
    approve(library, identifier)
    class BadProvider(FakeDecisionProvider):
        def decide(self, request):
            response = super().decide(request)
            response.evidence_ids = ["invented-record"]
            return response
    with pytest.raises(ValueError, match="outside"):
        library.compare(identifier, 1, identifier, 2, "same_event", BadProvider())
    assert library.db.execute("SELECT count(*) FROM library_decisions").fetchone()[0] == 0
    assert library.db.execute("SELECT count(*) FROM agent_proposals").fetchone()[0] == 0


def test_content_audit_detects_missing_original_and_changed_text(library, tmp_path):
    from archive.library_audit import audit_content
    identifier = library.ingest(entry(tmp_path))
    assert audit_content(library)["documents"] == 0
    approve(library, identifier)
    assert audit_content(library)["failed"] == 0
    with library.db:
        library.db.execute("UPDATE library_pages SET text='truncated' WHERE document_id=? AND number=1", (identifier,))
    assert audit_content(library)["failed"] == 1
    original = library.objects / library.document(identifier)["sha256"]
    original.unlink()
    assert audit_content(library)["failed"] == 1
