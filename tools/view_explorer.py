"""Serve the Explorer and open it in a browser.

The launcher logic lives here rather than in VIEW_EXPLORER.bat so that it can
be tested, and so the batch file stays short enough to read at a glance.

It finds the Explorer directory in whichever of the three layouts you have:

* the repository            -> apps/web-explorer/
* an unzipped scale artifact -> explorer/  (or artifacts/explorer/)
* already inside either one  -> .

Then it checks the exported read model is present, picks a free port, opens a
browser and serves until interrupted.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

#: Searched in order; the first directory holding index.html wins.
CANDIDATE_DIRS = (
    Path("apps/web-explorer"),
    Path("explorer"),
    Path("artifacts/explorer"),
    Path("."),
)

DATA_RELPATH = Path("data/explorer.json")
DEFAULT_PORT = 8000


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Same as the default handler, minus a log line per asset request."""

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - stdlib name
        return


def find_explorer_dir(root: Path) -> Path | None:
    for candidate in CANDIDATE_DIRS:
        directory = (root / candidate).resolve()
        if (directory / "index.html").is_file():
            return directory
    return None


def free_port(preferred: int = DEFAULT_PORT, *, attempts: int = 20) -> int:
    """Return ``preferred`` if it is free, else the next free port after it."""

    for offset in range(attempts):
        port = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    # Nothing in the range was free; let the OS choose.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def describe_data(directory: Path) -> str:
    """A one-line note about the exported read model, or why it is missing."""

    data = directory / DATA_RELPATH
    if not data.is_file():
        return (
            f"  !  {DATA_RELPATH.as_posix()} is missing.\n"
            "     The page will load but show no records. Generate it with:\n"
            "       archive-export-explorer --database <archive.sqlite> \\\n"
            f"         --output {(directory / DATA_RELPATH).as_posix()}\n"
            "     or copy it from a phase0-scale run's artifact."
        )
    try:
        import json

        payload = json.loads(data.read_text(encoding="utf-8"))
        count = payload.get("item_count", len(payload.get("items", [])))
        generated = payload.get("generated_at", "unknown time")
        return f"  data: {count} records, exported {generated}"
    except (OSError, ValueError) as exc:
        return f"  !  {DATA_RELPATH.as_posix()} could not be read: {exc}"


def serve(directory: Path, port: int, *, open_browser: bool = True) -> int:
    handler = functools.partial(_QuietHandler, directory=str(directory))
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        print(f"could not bind port {port}: {exc}", file=sys.stderr)
        return 1

    url = f"http://localhost:{port}/"
    print(f"  serving {directory}")
    print(describe_data(directory))
    print(f"\n  {url}\n\n  Press Ctrl+C (or close this window) to stop.\n")

    if open_browser:
        # A short delay so the browser does not race the first request.
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        server.shutdown()
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="view_explorer",
        description="Serve the September 11 Explorer and open it in a browser.",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=None,
        help="Explorer directory to serve; auto-detected when omitted.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-browser", action="store_true", help="Serve without opening a browser."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    directory = args.directory.resolve() if args.directory else find_explorer_dir(args.root)
    if directory is None or not (directory / "index.html").is_file():
        searched = ", ".join(path.as_posix() for path in CANDIDATE_DIRS)
        print(
            "Could not find the Explorer.\n"
            f"Looked for index.html in: {searched}\n"
            "Run this from the repository root, or from an unzipped\n"
            "phase0-scale-corpus artifact.",
            file=sys.stderr,
        )
        return 2

    return serve(directory, free_port(args.port), open_browser=not args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
