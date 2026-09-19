"""Source discovery and bounded, checkpointed bulk imports for the library."""
from __future__ import annotations

from contextlib import closing
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
import urllib.request

from archive.document_library import NoRedirect, encoded, now

PENTAGON_CATALOG = "https://www.archives.gov/research/pentagon-papers"
CHUNK = 1024 * 1024


def file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


class CatalogParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.link = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = {"links": [], "text": ""}
        if tag == "a" and self.row is not None:
            self.link = {"href": dict(attrs).get("href", ""), "text": ""}

    def handle_data(self, data):
        if self.row is not None:
            self.row["text"] += data
        if self.link is not None:
            self.link["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.link is not None:
            if self.row is not None:
                self.row["links"].append(self.link)
            self.link = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def pentagon_manifest(html: str) -> list[dict]:
    parser = CatalogParser()
    parser.feed(html)
    entries = []
    seen = set()
    for row in parser.rows:
        pdfs = [link for link in row["links"] if urlsplit(link["href"]).path.lower().endswith(".pdf")]
        if not pdfs:
            continue
        catalogs = [link for link in row["links"] if urlsplit(link["href"]).hostname == "catalog.archives.gov"]
        if len(pdfs) != 1 or len(catalogs) != 1:
            raise ValueError("Ambiguous PDF/catalog row; inspect the National Archives inventory")
        pdf, catalog = pdfs[0], catalogs[0]
        parsed = urlsplit(pdf["href"])
        if parsed.scheme != "https" or parsed.hostname not in {"www.archives.gov", "nara-media-001.s3.amazonaws.com"}:
            raise ValueError("Unexpected PDF origin in National Archives inventory")
        item_id = catalog["href"].rstrip("/").split("/")[-1]
        if not item_id.isdigit() or item_id in seen:
            raise ValueError("Missing or duplicate National Archives identifier")
        seen.add(item_id)
        size = re.search(r"([\d.]+)\s*MB", row["text"])
        entries.append(dict(collection="pentagon_papers", release_id="nara-2011",
            source_item_id=item_id, source_url=pdf["href"],
            title="Pentagon Papers — " + " ".join(pdf["text"].split()), format="pdf",
            publication_date="2011-06-13", catalog_url=catalog["href"],
            inventory_url=PENTAGON_CATALOG, rights="Public National Archives declassified release",
            advertised_bytes=int(float(size[1]) * 1_000_000) if size else None))
    if not entries:
        raise ValueError("No Pentagon Papers documents found; source layout may have changed")
    return entries


def discover_pentagon(output: Path, html_path: Path | None = None) -> list[dict]:
    if html_path is None:
        with urllib.request.urlopen(PENTAGON_CATALOG, timeout=30) as response:
            data = response.read(4 * CHUNK + 1)
        if len(data) > 4 * CHUNK:
            raise ValueError("Catalog exceeded size limit")
    else:
        data = html_path.read_bytes()
    entries = pentagon_manifest(data.decode("utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".source.html").write_bytes(data)
    output.with_suffix(".provenance.json").write_text(json.dumps({
        "inventory_url": PENTAGON_CATALOG, "captured_at": now(),
        "html_sha256": hashlib.sha256(data).hexdigest(), "items": len(entries),
    }, indent=2), encoding="utf-8")
    output.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    return entries


class DownloadLimit(ValueError):
    pass


def preserve_stream(stream, objects: Path, max_bytes: int, expected_sha: str | None = None, on_bytes=None, expected_bytes=None) -> tuple[Path, int]:
    """Hash and stage chunks; incomplete or over-budget files never become objects."""
    objects.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(dir=objects, prefix=".download-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            while chunk := stream.read(min(CHUNK, max_bytes - size + 1)):
                size += len(chunk)
                if on_bytes:
                    on_bytes(len(chunk))
                if size > max_bytes:
                    raise DownloadLimit("File exceeds remaining batch or per-file byte limit")
                handle.write(chunk)
                sha.update(chunk)
        except BaseException:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        if not size:
            raise ValueError("Empty source file")
        if expected_bytes is not None and size != expected_bytes:
            raise ValueError("Incomplete download: received size differs from Content-Length")
        checksum = sha.hexdigest()
        if expected_sha and checksum != expected_sha:
            raise ValueError("Source checksum mismatch")
        target = objects / checksum
        if target.exists():
            if file_digest(target) != checksum:
                raise ValueError("Preserved object failed integrity check")
        else:
            # Same-filesystem hard link is atomic and never overwrites another object.
            try:
                target.hardlink_to(temporary)
            except FileExistsError:
                if file_digest(target) != checksum:
                    raise ValueError("Concurrent preserved object failed integrity check")
        return target, size
    finally:
        temporary.unlink(missing_ok=True)


def fetch_object(entry: dict, base: Path, objects: Path, max_bytes: int, on_bytes=None) -> tuple[Path, int]:
    if entry.get("path"):
        with (base / entry["path"]).open("rb") as handle:
            return preserve_stream(handle, objects, max_bytes, entry.get("sha256"), on_bytes)
    if urlsplit(entry["source_url"]).scheme != "https":
        raise ValueError("Remote retrieval requires HTTPS")
    request = urllib.request.Request(entry["source_url"], headers={"User-Agent": "HistoricalEvidenceEngine/0.2"})
    with closing(urllib.request.build_opener(NoRedirect).open(request, timeout=60)) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise DownloadLimit("Advertised file size exceeds remaining batch or per-file byte limit")
        return preserve_stream(response, objects, max_bytes, entry.get("sha256"), on_bytes,
            expected_bytes=int(length) if length else None)


def bulk_ingest(library, path: Path, *, max_file_bytes=600 * CHUNK,
                max_total_bytes=1024 * CHUNK, limit=None, refresh=False, progress=None) -> dict:
    entries = json.loads(path.read_text(encoding="utf-8-sig"))
    if max_file_bytes <= 0 or max_total_bytes <= 0 or (limit is not None and limit < 1):
        raise ValueError("Byte budgets and item limit must be positive")
    library.register_inventory(entries)
    transferred, results = 0, []
    def account(size):
        nonlocal transferred
        transferred += size
    for entry in entries[:limit]:
        metadata = {key: value for key, value in entry.items() if key != "path"}
        result = {"source_item_id": entry["source_item_id"]}
        try:
            cached = library.db.execute("SELECT id,sha256 FROM library_documents WHERE metadata_json=? ORDER BY retrieved_at DESC LIMIT 1", (encoded(metadata),)).fetchone()
            if cached and not refresh:
                if file_digest(library.objects / cached["sha256"]) != cached["sha256"]:
                    raise ValueError("Preserved object failed integrity check")
                result.update(status="processed", document_id=cached["id"], resumed=True)
            else:
                # Retry extraction from a completed download after a previous parse failure.
                saved = library.db.execute("SELECT sha256 FROM library_downloads WHERE entry_json=?", (encoded(metadata),)).fetchone()
                if saved and not refresh:
                    target = library.objects / saved["sha256"]
                    if file_digest(target) != saved["sha256"]:
                        raise ValueError("Cached download failed integrity check")
                else:
                    if transferred >= max_total_bytes:
                        raise DownloadLimit("Batch byte budget exhausted")
                    target, size = fetch_object(entry, path.parent, library.objects, min(max_file_bytes, max_total_bytes - transferred), account)
                    with library.db:
                        library.db.execute("INSERT OR REPLACE INTO library_downloads VALUES(?,?,?)", (encoded(metadata), target.name, now()))
                identifier = library.ingest_preserved(entry, target)
                result.update(status="processed", document_id=identifier, resumed=False)
        except DownloadLimit as exc:
            result.update(status="deferred", error=str(exc))
        except Exception as exc:
            result.update(status="failed", error=str(exc))
        library.record_attempt(entry, result)
        results.append(result)
        if progress:
            progress(result)
    return {"inventoried": len(entries), "bytes_transferred": transferred, "results": results}
