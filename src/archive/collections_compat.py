"""Resolving the active collection for the legacy ``archive`` API.

Functions such as ``archive.work_queue.build_work_queue`` predate the
collection abstraction and take no collection argument. They now resolve one
here.

**Transitional default.** When no collection is named, ``september11`` is
used, so every existing command, workflow and script keeps its previous
behaviour. This default is a compatibility measure, not a design position, and
is expected to be removed once callers pass ``--collection`` (or set
``HISTORICAL_ENGINE_COLLECTION``) explicitly. It lives here — in the
compatibility layer — precisely so that no collection name appears anywhere
under ``src/historical_engine/``.
"""

from __future__ import annotations

import os

from historical_engine.collection import Collection

#: TRANSITIONAL — see the module docstring.
DEFAULT_COLLECTION_ID = "september11"

#: Overrides the transitional default without touching any call site.
COLLECTION_ENV_VAR = "HISTORICAL_ENGINE_COLLECTION"


def _ensure_collections_registered() -> None:
    # Imported lazily: importing a collection pulls in its adapters, and the
    # engine must stay usable without any collection installed.
    import evidence_collections  # noqa: F401  (installs the registry bootstrap)


def default_collection_id() -> str:
    return os.environ.get(COLLECTION_ENV_VAR, "").strip() or DEFAULT_COLLECTION_ID


def resolve_collection(collection: Collection | str | None = None) -> Collection:
    """Return a collection from an instance, an id, or the transitional default."""

    if collection is not None and not isinstance(collection, str):
        return collection

    from historical_engine.collection_registry import get_collection

    _ensure_collections_registered()
    return get_collection(collection or default_collection_id())
