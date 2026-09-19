"""Check public document bytes and stored contents against preserved sources."""
import json
from archive.document_library import extract_pages, now
from archive.library_sources import file_digest


def audit_content(library):
    results = []
    for doc in library.db.execute("SELECT * FROM library_documents WHERE public=1 ORDER BY id").fetchall():
        result = dict(document_id=doc["id"], collection=doc["collection"], title=doc["title"], status="ok")
        try:
            path = library.objects / doc["sha256"]
            if file_digest(path) != doc["sha256"]:
                raise ValueError("Preserved file hash mismatch")
            pages = library.db.execute("SELECT number,text,needs_ocr FROM library_pages WHERE document_id=? ORDER BY number", (doc["id"],)).fetchall()
            result.update(bytes=path.stat().st_size, pages=len(pages),
                          pages_without_text=sum(not p["text"].strip() for p in pages))
            if doc["format"] == "pdf":
                import pymupdf
                with pymupdf.open(path) as pdf:
                    if len(pdf) != len(pages):
                        raise ValueError("Preserved PDF and stored page counts differ")
                result["content_kind"] = "preserved_pdf"
            else:
                metadata = json.loads(doc["metadata_json"])
                result["content_kind"] = metadata.get("content_kind", "metadata_only" if doc["format"] == "record" else "published_text")
                extracted, _ = extract_pages(path.read_bytes(), doc["format"])
                if extracted != [p["text"] for p in pages]:
                    raise ValueError("Stored text differs from preserved source")
            if [p["number"] for p in pages] != list(range(1, len(pages) + 1)):
                raise ValueError("Non-contiguous page numbers")
        except Exception as exc:
            result.update(status="failed", error=str(exc))
        results.append(result)
    return dict(audited_at=now(), documents=len(results), failed=sum(r["status"] == "failed" for r in results),
                scope="Local byte integrity, PDF page counts, and text-record extraction; not independent validation of source completeness or claims.", results=results)
