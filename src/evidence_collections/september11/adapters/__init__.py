"""Adapters used by the September 11 collection.

Two kinds live here:

* **Configured generic adapters** — the Internet Archive, Omeka and ArcGIS
  feature-service adapters are generic protocol readers; this collection binds
  them to specific endpoints, source ids and collection ids.
* **Collection-specific adapters** — the NIST repository and NIST organized-media
  readers have no generic equivalent worth extracting today and are re-exported
  from their original module paths so nothing breaks.

The implementations still live under ``archive.adapters`` so that every
existing import path, test and CI workflow keeps working.
"""

from __future__ import annotations

from archive.adapters.arcgis_photo_map import ArcGisPhotoMapAdapter
from archive.adapters.internet_archive import InternetArchiveAdapter
from archive.adapters.nist_organized import NistOrganizedMediaAdapter
from archive.adapters.nist_wtc import NistWtcRepositoryAdapter
from archive.adapters.september11digital import September11DigitalArchiveAdapter

__all__ = [
    "ArcGisPhotoMapAdapter",
    "InternetArchiveAdapter",
    "NistOrganizedMediaAdapter",
    "NistWtcRepositoryAdapter",
    "September11DigitalArchiveAdapter",
]
