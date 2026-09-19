"""Operator CLI and loopback-only, read-only document library preview."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
from urllib.parse import parse_qs, urlsplit

from archive.document_library import DocumentLibrary, digest


class LibraryServer(ThreadingHTTPServer):
    allow_reuse_address = False


def handler_for(database, objects):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            library = DocumentLibrary(database, objects)
            try:
                if parsed.path == "/":
                    return self.respond(200, Path(__file__).with_name("library.html").read_bytes(), "text/html; charset=utf-8")
                if parsed.path == "/library.js":
                    return self.respond(200, Path(__file__).with_name("library.js").read_bytes(), "text/javascript; charset=utf-8")
                if parsed.path == "/api/search":
                    values = parse_qs(parsed.query)
                    return self.respond(200, library.search(values.get("q", [""])[0], values.get("collection", [""])[0], offset=int(values.get("offset", ["0"])[0])))
                if parsed.path == "/api/inventory":
                    return self.respond(200, library.inventory_coverage())
                if parsed.path == "/api/coverage":
                    return self.respond(200, library.coverage(public_only=True))
                parts = parsed.path.strip("/").split("/")
                if len(parts) in (3, 4, 5) and parts[:2] == ["api", "documents"]:
                    doc = library.document(parts[2], include_pages=False)
                    if doc:
                        if len(parts) == 3:
                            return self.respond(200, doc)
                        if len(parts) == 5 and parts[3] == "pages":
                            page = library.page(parts[2], int(parts[4]))
                            if page:
                                return self.respond(200, page)
                        if parts[3] == "original":
                            from archive.library_sources import file_digest
                            path = library.objects / doc["sha256"]
                            if file_digest(path) != doc["sha256"]:
                                return self.respond(409, {"error": "Original failed integrity check"})
                            self.send_response(200)
                            self.send_header("Content-Type", "application/octet-stream")
                            self.send_header("Content-Length", str(path.stat().st_size))
                            self.send_header("Content-Disposition", f'attachment; filename="{doc["id"]}.{ "pdf" if doc["format"] == "pdf" else "txt"}"')
                            self.send_header("X-Content-Type-Options", "nosniff")
                            self.send_header("Cache-Control", "no-store")
                            self.end_headers()
                            with path.open("rb") as handle:
                                shutil.copyfileobj(handle, self.wfile, length=1024 * 1024)
                            return
                self.respond(404, {"error": "Not found"})
            except (ValueError, TypeError):
                self.respond(400, {"error": "Invalid request"})
            except Exception:
                self.respond(500, {"error": "Unable to read library"})
            finally:
                library.close()

        def respond(self, status, data, content_type="application/json; charset=utf-8", filename=None):
            payload = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("artifacts/library.sqlite"))
    parser.add_argument("--objects", type=Path, default=Path("artifacts/library-objects"))
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("manifest", type=Path)
    discover = commands.add_parser("discover-pentagon")
    discover.add_argument("--output", type=Path, required=True)
    discover.add_argument("--html", type=Path)
    inventory = commands.add_parser("inventory")
    inventory.add_argument("manifest", type=Path, nargs="?")
    bulk = commands.add_parser("bulk-ingest")
    bulk.add_argument("manifest", type=Path)
    bulk.add_argument("--max-file-mib", type=int, default=600)
    bulk.add_argument("--max-total-mib", type=int, default=1024)
    bulk.add_argument("--limit", type=int)
    bulk.add_argument("--refresh", action="store_true")
    cablegate = commands.add_parser("fetch-cablegate")
    cablegate.add_argument("--output-dir", type=Path, default=Path("artifacts/cablegate-sample"))
    cablegate.add_argument("--limit", type=int, default=1000)
    records = commands.add_parser("import-records")
    records.add_argument("path", type=Path)
    records.add_argument("--collection", required=True)
    records.add_argument("--release-id", required=True)
    search = commands.add_parser("search")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--collection", default="")
    commands.add_parser("coverage")
    review = commands.add_parser("publication")
    review.add_argument("document_id")
    review.add_argument("--public", action="store_true", help="Omit to withdraw a document")
    review.add_argument("--reviewer", required=True)
    review.add_argument("--note", required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("left")
    compare.add_argument("right")
    compare.add_argument("--left-page", type=int, default=1)
    compare.add_argument("--right-page", type=int, default=1)
    compare.add_argument("--question", choices=["same_event", "same_entity", "duplicate_or_derivative"], default="same_event")
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8879)
    args = parser.parse_args(argv)
    if args.command == "serve":
        server = LibraryServer(("127.0.0.1", args.port), handler_for(args.database, args.objects))
        print(f"Document library: http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    library = DocumentLibrary(args.database, args.objects)
    try:
        if args.command == "ingest":
            result = library.ingest_manifest(args.manifest)
        elif args.command == "discover-pentagon":
            from archive.library_sources import discover_pentagon
            entries = discover_pentagon(args.output, args.html)
            library.register_inventory(entries)
            result = {"items": len(entries), "manifest": str(args.output)}
        elif args.command == "inventory":
            if args.manifest:
                library.register_inventory(json.loads(args.manifest.read_text(encoding="utf-8-sig")))
            result = library.inventory_coverage()
        elif args.command == "bulk-ingest":
            from archive.library_sources import bulk_ingest
            result = bulk_ingest(library, args.manifest, max_file_bytes=args.max_file_mib * 1024**2,
                max_total_bytes=args.max_total_mib * 1024**2, limit=args.limit, refresh=args.refresh,
                progress=lambda row: print(json.dumps(row), flush=True))
        elif args.command == "fetch-cablegate":
            from archive.library_cablegate import fetch_cablegate
            result = fetch_cablegate(library, args.output_dir, args.limit)
        elif args.command == "import-records":
            result = library.import_records(args.path, args.collection, args.release_id)
        elif args.command == "search":
            result = library.search(args.query, args.collection)
        elif args.command == "coverage":
            result = library.coverage()
        elif args.command == "publication":
            library.publish(args.document_id, args.public, args.reviewer, args.note)
            result = {"document_id": args.document_id, "public": args.public}
        else:
            from historical_engine.ai.jev import JevDecisionProvider
            result = library.compare(args.left, args.left_page, args.right, args.right_page, args.question, JevDecisionProvider.from_env())
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.command == "bulk-ingest":
            return int(any(row["status"] == "failed" for row in result["results"]))
        if args.command == "fetch-cablegate":
            return int(result["failed"] > 0)
        return int(args.command in {"ingest", "import-records"} and any(row["status"] == "failed" for row in result))
    finally:
        library.close()


if __name__ == "__main__":
    raise SystemExit(main())
