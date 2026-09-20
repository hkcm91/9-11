"""Operator CLI and loopback document reader with explicit Jev comparisons."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
from threading import Lock
from urllib.parse import parse_qs, urlsplit

from archive.document_library import DocumentLibrary, digest


class LibraryServer(ThreadingHTTPServer):
    allow_reuse_address = False


def handler_for(database, objects, *, jev_factory=None):
    from historical_engine.ai.jev import JevDecisionProvider
    from historical_engine.ai.providers import AiProviderError
    comparison_lock = Lock()

    def provider_status():
        provider = (jev_factory or JevDecisionProvider.from_env)()
        ready = True if jev_factory else provider.transport.config.ready_for_transport
        return provider, {"configured": ready, "model": provider.model,
                          "message": "Ready to request a comparison. Connection is checked when you compare."
                          if ready else "Jev needs a server-side TypeSafe API key before comparisons can run."}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path not in {"/api/compare", "/api/completion/verify", "/api/completion/match", "/api/digest", "/api/research", "/api/leads/scan", "/api/leads/run", "/api/leads/assess", "/api/leads/review"}:
                return self.respond(404, {"error": "Not found"})
            # No cross-origin browser can initiate a paid call or write proposals.
            host = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if (host not in allowed or self.headers.get("Origin") != "http://" + host
                    or self.headers.get("X-Archive-Request") != "1"):
                return self.respond(403, {"error": "Open the archive locally to compare pages."})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.respond(415, {"error": "Expected JSON"})
            library = None
            acquired = False
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    return self.respond(413, {"error": "Invalid request size"})
                values = json.loads(self.rfile.read(length))
                if self.path.startswith('/api/completion/'):
                    from archive.library_completion import CompletionDesk
                    if not isinstance(values, dict) or not all(isinstance(values.get(k), str) for k in ('collection','release_id')):
                        raise ValueError('Choose a collection and release')
                    acquired = comparison_lock.acquire(blocking=False)
                    if not acquired:
                        return self.respond(429, {'error': 'An archive action is already running.'})
                    library = DocumentLibrary(database, objects)
                    desk = CompletionDesk(library)
                    if self.path.endswith('/verify'):
                        return self.respond(200, desk.verify(values['collection'], values['release_id']))
                    if not all(isinstance(values.get(k), str) for k in ('source_item_id','candidate')):
                        raise ValueError('Choose an expected item and candidate document')
                    provider, status = provider_status()
                    if not status['configured']:
                        return self.respond(503, {'error': status['message']})
                    return self.respond(200, desk.match(values['collection'], values['release_id'], values['source_item_id'], values['candidate'], provider))
                if self.path == '/api/digest':
                    from archive.library_digest import DocumentDigest
                    if not isinstance(values, dict) or not isinstance(values.get('id'), str):
                        raise ValueError('Choose a document')
                    acquired = comparison_lock.acquire(blocking=False)
                    if not acquired:
                        return self.respond(429, {'error': 'Another Jev action is running. Try again shortly.'})
                    provider, status = provider_status()
                    if not status['configured']:
                        return self.respond(503, {'error': status['message']})
                    library = DocumentLibrary(database, objects)
                    return self.respond(200, DocumentDigest(library).build(values['id'], provider))
                if self.path == '/api/research':
                    from archive.library_research import ResearchDesk
                    if not isinstance(values, dict):
                        raise ValueError('Expected an object')
                    acquired = comparison_lock.acquire(blocking=False)
                    if not acquired:
                        return self.respond(429, {'error': 'Another investigation is running. Try again shortly.'})
                    provider, status = provider_status()
                    if not status['configured']:
                        return self.respond(503, {'error': status['message']})
                    library = DocumentLibrary(database, objects)
                    return self.respond(200, ResearchDesk(library).run(values.get('question'), provider,
                        values.get('mode', 'relevance'), values.get('collection', ''), values.get('budget', 3)))
                if self.path.startswith('/api/leads/'):
                    from archive.library_leads import LeadInbox
                    if not isinstance(values, dict):
                        raise ValueError('Expected an object')
                    acquired = comparison_lock.acquire(blocking=False)
                    if not acquired:
                        return self.respond(429, {'error': 'Another archive action is running. Try again shortly.'})
                    library = DocumentLibrary(database, objects)
                    inbox = LeadInbox(library)
                    if self.path == '/api/leads/scan':
                        return self.respond(200, inbox.scan())
                    if self.path == '/api/leads/run':
                        provider, status = provider_status()
                        if not status['configured']:
                            return self.respond(503, {'error': status['message']})
                        return self.respond(200, inbox.run(provider))
                    if not isinstance(values.get('id'), str):
                        raise ValueError('Choose a lead')
                    if self.path == '/api/leads/review':
                        return self.respond(200, inbox.review(values['id'], values.get('status'), values.get('note')))
                    provider, status = provider_status()
                    if not status['configured']:
                        return self.respond(503, {'error': status['message']})
                    return self.respond(200, inbox.assess(values['id'], provider))
                if not isinstance(values, dict) or values.get("question") not in {
                        "same_event", "same_entity", "duplicate_or_derivative"}:
                    raise ValueError("Choose a supported comparison question.")
                for side in ("left", "right"):
                    if not isinstance(values.get(side), str) or len(values[side]) != 64:
                        raise ValueError("Choose two document pages.")
                    number = values.get(side + "_page")
                    if type(number) is not int or number < 1:
                        raise ValueError("Choose valid page numbers.")
                acquired = comparison_lock.acquire(blocking=False)
                if not acquired:
                    return self.respond(429, {"error": "A comparison is already running. Try again when it finishes."})
                provider, status = provider_status()
                if not status["configured"]:
                    return self.respond(503, {"error": status["message"]})
                library = DocumentLibrary(database, objects)
                result = library.compare(values["left"], values["left_page"], values["right"],
                                         values["right_page"], values["question"], provider)
                return self.respond(200, result)
            except AiProviderError:
                return self.respond(502, {"error": "Jev could not complete the comparison. Check the server credentials and connection, then retry."})
            except (ValueError, TypeError, KeyError) as exc:
                return self.respond(400, {"error": str(exc) if isinstance(exc, ValueError) else "Invalid comparison request"})
            except Exception:
                return self.respond(500, {"error": "Unable to complete comparison"})
            finally:
                if library:
                    library.close()
                if acquired:
                    comparison_lock.release()

        def do_GET(self):
            parsed = urlsplit(self.path)
            library = DocumentLibrary(database, objects)
            try:
                if parsed.path == "/":
                    return self.respond(200, Path(__file__).with_name("library.html").read_bytes(), "text/html; charset=utf-8")
                if parsed.path == "/library.js":
                    return self.respond(200, Path(__file__).with_name("library.js").read_bytes(), "text/javascript; charset=utf-8")
                if parsed.path == "/api/jev/status":
                    _, status = provider_status()
                    return self.respond(200, status)
                if parsed.path == '/api/leads':
                    from archive.library_leads import LeadInbox
                    return self.respond(200, LeadInbox(library).list())
                if parsed.path == '/api/research' or parsed.path.startswith('/api/research/'):
                    from archive.library_research import ResearchDesk
                    desk = ResearchDesk(library)
                    return self.respond(200, desk.history() if parsed.path == '/api/research' else desk.get(parsed.path.rsplit('/', 1)[-1]))
                if parsed.path == "/api/search":
                    values = parse_qs(parsed.query)
                    from archive.library_digest import decorate
                    return self.respond(200, [decorate(library, row) for row in library.search(values.get("q", [""])[0], values.get("collection", [""])[0], offset=int(values.get("offset", ["0"])[0]))])
                if parsed.path == "/api/inventory":
                    return self.respond(200, library.inventory_coverage())
                if parsed.path == "/api/coverage":
                    return self.respond(200, library.coverage(public_only=True))
                if parsed.path == '/api/wikileaks/bulk':
                    from archive.library_wikileaks_bulk import bulk_status
                    return self.respond(200, bulk_status(library, Path(database).parent / 'wikileaks-bulk'))
                if parsed.path in {'/api/completion','/api/completion/items'}:
                    from archive.library_completion import CompletionDesk
                    desk = CompletionDesk(library)
                    if parsed.path == '/api/completion':
                        return self.respond(200, desk.releases())
                    values = parse_qs(parsed.query)
                    rows = desk.items(values.get('collection',[''])[0], values.get('release_id',[''])[0])
                    stage = values.get('stage',[''])[0]
                    if stage:
                        rows = [r for r in rows if r['stage']==stage]
                    offset = max(0,int(values.get('offset',['0'])[0]))
                    return self.respond(200, {'total':len(rows), 'items':rows[offset:offset+50]})
                parts = parsed.path.strip("/").split("/")
                if len(parts) in (3, 4, 5, 6) and parts[:2] == ["api", "documents"]:
                    doc = library.document(parts[2], include_pages=False)
                    if doc:
                        from archive.library_digest import DocumentDigest, decorate, file_stem
                        doc = decorate(library, doc)
                        if len(parts) == 3:
                            return self.respond(200, doc)
                        if len(parts) == 4 and parts[3] == 'digest':
                            return self.respond(200, DocumentDigest(library).get(doc['id']))
                        if len(parts) == 4 and parts[3] == 'brief':
                            briefs = DocumentDigest(library)
                            brief = briefs.get(doc['id'])
                            if not brief:
                                return self.respond(404, {'error': 'Create a reading brief first'})
                            return self.respond(200, briefs.markdown(doc['id']).encode('utf-8'), 'text/markdown; charset=utf-8', brief['filename'])
                        if len(parts) == 6 and parts[3] == "pages" and parts[5] == "image" and doc["format"] == "pdf":
                            number = int(parts[4])
                            if not library.page(parts[2], number):
                                return self.respond(404, {"error": "Page not found"})
                            import pymupdf
                            with pymupdf.open(library.objects / doc["sha256"]) as pdf:
                                page = pdf[number - 1]
                                scale = min(2, 1400 / max(page.rect.width, page.rect.height))
                                picture = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                                return self.respond(200, picture.tobytes("png"), "image/png")
                        if len(parts) == 5 and parts[3] == "pages":
                            page = library.page(parts[2], int(parts[4]))
                            if page:
                                return self.respond(200, page)
                        if len(parts) == 4 and parts[3] == "original":
                            from archive.library_sources import file_digest
                            path = library.objects / doc["sha256"]
                            if file_digest(path) != doc["sha256"]:
                                return self.respond(409, {"error": "Original failed integrity check"})
                            self.send_response(200)
                            self.send_header("Content-Type", "application/octet-stream")
                            self.send_header("Content-Length", str(path.stat().st_size))
                            extension = {"pdf": "pdf", "warlog_html": "html", "record": "json"}.get(doc["format"], "txt")
                            self.send_header("Content-Disposition", f'attachment; filename="{file_stem(doc["display_title"], doc["id"])}.{extension}"')
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
    full_cablegate = commands.add_parser("fetch-cablegate-full")
    full_cablegate.add_argument("--output-dir", type=Path, default=Path("artifacts/wikileaks-bulk"))
    full_cablegate.add_argument("--max-records", type=int)
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
    scopes = commands.add_parser('completion-scopes')
    scopes.add_argument('path', type=Path)
    completion = commands.add_parser('completion')
    completion.add_argument('--collection')
    completion.add_argument('--release-id')
    completion.add_argument('--verify', action='store_true')
    commands.add_parser("audit-content")
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
        elif args.command == "fetch-cablegate-full":
            from archive.library_wikileaks_bulk import fetch_full
            result = fetch_full(library, args.output_dir, args.max_records,
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
        elif args.command in {'completion', 'completion-scopes'}:
            from archive.library_completion import CompletionDesk
            desk = CompletionDesk(library)
            if args.command == 'completion-scopes':
                scopes = json.loads(args.path.read_text(encoding='utf-8-sig'))
                desk.register(scopes)
                result = {'registered':len(scopes)}
            elif args.verify:
                if not args.collection or not args.release_id:
                    parser.error('--verify requires --collection and --release-id')
                result = desk.verify(args.collection,args.release_id)
            elif args.collection and args.release_id:
                result = desk.items(args.collection,args.release_id)
            else:
                result = desk.releases()
        elif args.command == "audit-content":
            from archive.library_audit import audit_content
            result = audit_content(library)
        elif args.command == "publication":
            library.publish(args.document_id, args.public, args.reviewer, args.note)
            result = {"document_id": args.document_id, "public": args.public}
        else:
            from historical_engine.ai.jev import JevDecisionProvider
            result = library.compare(args.left, args.left_page, args.right, args.right_page, args.question, JevDecisionProvider.from_env())
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.command == "bulk-ingest":
            return int(any(row["status"] == "failed" for row in result["results"]))
        if args.command in {"fetch-cablegate", "audit-content"}:
            return int(result["failed"] > 0)
        return int(args.command in {"ingest", "import-records"} and any(row["status"] == "failed" for row in result))
    finally:
        library.close()


if __name__ == "__main__":
    raise SystemExit(main())
