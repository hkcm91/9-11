import io
import json
from pathlib import Path

from evidence_collections.wikileaks.remote_sources import (
    discover_cablegate_csv_url,
    stream_csv_sample,
)


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = io.BytesIO(body)

    def read(self, *args):
        return self._body.read(*args)

    def readline(self, *args):
        return self._body.readline(*args)

    def __iter__(self):
        return iter(self._body)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        self._body.close()


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
        lambda url, timeout=30.0: FakeResponse(json.dumps(payload).encode("utf-8")),
    )

    url = discover_cablegate_csv_url()

    assert url.endswith("/wikileaks-cables-csv/cables.csv")


def test_stream_csv_sample_writes_only_requested_records(tmp_path: Path, monkeypatch) -> None:
    body = (
        "id,title,summary\n"
        "1,First,Alpha\n"
        "2,Second,Beta\n"
        "3,Third,Gamma\n"
    ).encode("utf-8")

    monkeypatch.setattr(
        "evidence_collections.wikileaks.remote_sources._open",
        lambda url, timeout=60.0: FakeResponse(body),
    )

    output = tmp_path / "sample.csv"
    result = stream_csv_sample(
        "https://example.test/data.csv",
        output,
        limit=2,
    )

    assert result["records"] == 2
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert "Third" not in output.read_text(encoding="utf-8")
