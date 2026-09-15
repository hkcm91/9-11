from __future__ import annotations

from archive.adapters.nist_wtc import NistWtcRepositoryAdapter


def test_extract_repository_links_prefers_real_links_and_adds_fallbacks() -> None:
    adapter = NistWtcRepositoryAdapter(request_delay_s=0)
    html = '''
    <html><body>
      <a href="https://drive.google.com/drive/folders/abc">Organized Photos and Video Clips</a>
      <a href="https://www.nist.gov/about">About NIST</a>
    </body></html>
    '''
    rows = adapter.extract_repository_links(html)
    labels = {row["label"] for row in rows}
    organized = next(row for row in rows if row["label"] == "Organized Photos and Video Clips")

    assert organized["url"] == "https://drive.google.com/drive/folders/abc"
    assert "fallback" not in organized
    assert "Original Video from Tapes" in labels
    assert "Computer Simulations" in labels


def test_extracts_nist_google_drive_image_links_by_alt_text() -> None:
    adapter = NistWtcRepositoryAdapter(request_delay_s=0)
    html = '''
      <a href="https://googledrive.nist.gov/folders/organized"><img alt="WTC - Organized Photos for Repository"></a>
    '''
    rows = adapter.extract_repository_links(html)
    organized = next(row for row in rows if row["label"] == "Organized Photos and Video Clips")
    assert organized["url"] == "https://googledrive.nist.gov/folders/organized"
    assert organized["source_label"] == "WTC - Organized Photos for Repository"
    assert "fallback" not in organized


def test_normalize_marks_repository_entry() -> None:
    adapter = NistWtcRepositoryAdapter(request_delay_s=0)
    item = adapter.normalize({
        "label": "Original Video from Tapes",
        "url": "https://drive.google.com/drive/folders/example",
        "host": "drive.google.com",
    })

    assert item.source_id == "nist-wtc-disaster-repository"
    assert item.title_raw == "Original Video from Tapes"
    assert item.media_type_raw == "repository_entry"
    assert item.collection_raw == "NIST World Trade Center Disaster Investigation Materials"
    assert "item-specific" in (item.rights_raw or "").lower()
