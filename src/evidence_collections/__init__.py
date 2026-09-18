"""Collections running on the Historical Evidence Engine.

Each subpackage is one historical corpus: its ontology, its source registry,
its rules, its hooks and its adapters. The engine never imports this package;
this package imports the engine and registers itself with it.

Naming note: the requested directory name was ``collections``. ``src/`` is on
``pythonpath``, so a top-level package by that name would shadow the standard
library's ``collections`` module and break the interpreter. The directory is
therefore ``evidence_collections``; the separation is unchanged.
"""

from __future__ import annotations

from historical_engine.collection_registry import register_collection, set_bootstrap

#: Built-in collections, as ``id -> factory import path``. Kept as lazy import
#: strings so that importing this package does not pull in every collection's
#: adapters.
BUILTIN_COLLECTIONS: dict[str, str] = {
    "september11": "evidence_collections.september11:build_collection",
    "demo_history": "evidence_collections.demo_history:build_collection",
    "wikileaks": "evidence_collections.wikileaks:build_collection",
}


def _load(spec: str):
    from importlib import import_module

    module_name, _, attribute = spec.partition(":")
    return getattr(import_module(module_name), attribute)


def install_builtin_collections() -> None:
    """Register every built-in collection with the engine registry."""

    for spec in BUILTIN_COLLECTIONS.values():
        register_collection(_load(spec)(), replace=True)


# Installing the bootstrap rather than running it keeps collection imports lazy:
# nothing is constructed until something actually asks the registry for a
# collection.
set_bootstrap(install_builtin_collections)

__all__ = ["BUILTIN_COLLECTIONS", "install_builtin_collections"]
