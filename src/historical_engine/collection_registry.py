"""Collection registry.

The engine must be able to look a collection up by id without importing any
collection package — otherwise the dependency arrow points the wrong way and
the engine stops being reusable. Collections therefore *register themselves*,
and the engine is told how to discover them through a bootstrap callable that
the application layer installs.

``src/evidence_collections/__init__.py`` installs the built-in bootstrap; the
engine itself names no collection.
"""

from __future__ import annotations

import threading
from typing import Callable, Iterable

from historical_engine.collection import Collection

_LOCK = threading.RLock()
_COLLECTIONS: dict[str, Collection] = {}
_BOOTSTRAP: Callable[[], None] | None = None
_BOOTSTRAPPED = False


class UnknownCollectionError(KeyError):
    """Raised when a collection id has not been registered."""

    def __init__(self, collection_id: str, known: Iterable[str]) -> None:
        known_text = ", ".join(sorted(known)) or "<none registered>"
        super().__init__(f"unknown collection '{collection_id}'. Registered: {known_text}")
        self.collection_id = collection_id


def set_bootstrap(bootstrap: Callable[[], None] | None) -> None:
    """Install the callable that registers the available collections."""

    global _BOOTSTRAP, _BOOTSTRAPPED
    with _LOCK:
        _BOOTSTRAP = bootstrap
        _BOOTSTRAPPED = False


def _ensure_bootstrapped() -> None:
    global _BOOTSTRAPPED
    with _LOCK:
        if _BOOTSTRAPPED or _BOOTSTRAP is None:
            return
        # Set the flag first: a bootstrap that registers collections will call
        # back into this module, and re-entering must not loop.
        _BOOTSTRAPPED = True
        _BOOTSTRAP()


def register_collection(collection: Collection, *, replace: bool = False) -> Collection:
    with _LOCK:
        existing = _COLLECTIONS.get(collection.id)
        if existing is not None and not replace and existing is not collection:
            raise ValueError(f"collection '{collection.id}' is already registered")
        _COLLECTIONS[collection.id] = collection
    return collection


def unregister_collection(collection_id: str) -> None:
    with _LOCK:
        _COLLECTIONS.pop(collection_id, None)


def get_collection(collection_id: str) -> Collection:
    _ensure_bootstrapped()
    with _LOCK:
        try:
            return _COLLECTIONS[collection_id]
        except KeyError:
            raise UnknownCollectionError(collection_id, _COLLECTIONS) from None


def available_collections() -> list[str]:
    _ensure_bootstrapped()
    with _LOCK:
        return sorted(_COLLECTIONS)


def iter_collections() -> list[Collection]:
    _ensure_bootstrapped()
    with _LOCK:
        return [_COLLECTIONS[key] for key in sorted(_COLLECTIONS)]


def reset_registry() -> None:
    """Test helper: forget every registration and re-run bootstrap on demand."""

    global _BOOTSTRAPPED
    with _LOCK:
        _COLLECTIONS.clear()
        _BOOTSTRAPPED = False
