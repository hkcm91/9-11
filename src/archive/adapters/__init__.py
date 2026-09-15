"""Source adapters for public archival collections."""

from .arcgis_photo_map import ArcGisPhotoMapAdapter
from .internet_archive import InternetArchiveAdapter
from .nist_organized import NistOrganizedMediaAdapter
from .nist_wtc import NistWtcRepositoryAdapter
from .september11digital import September11DigitalArchiveAdapter

__all__ = [
    "ArcGisPhotoMapAdapter",
    "InternetArchiveAdapter",
    "NistOrganizedMediaAdapter",
    "NistWtcRepositoryAdapter",
    "September11DigitalArchiveAdapter",
]
