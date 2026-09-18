from __future__ import annotations

import pytest

from archive.models import SourceItem
from historical_engine.collection import BaseCollection
from historical_engine.collection_registry import (
    UnknownCollectionError,
    available_collections,
    get_collection,
    register_collection,
    unregister_collection,
)
from historical_engine.ontology import OntologyError


def _item(**kwargs) -> SourceItem:
    payload = {
        "id": "item:1",
        "source_id": "some-source",
        "source_item_id": "1",
        "source_url": "https://example.test/1",
    }
    payload.update(kwargs)
    return SourceItem(**payload)


def test_builtin_collections_are_registered() -> None:
    assert "september11" in available_collections()
    assert "demo_history" in available_collections()


def test_unknown_collection_names_the_registered_ones() -> None:
    with pytest.raises(UnknownCollectionError) as excinfo:
        get_collection("no-such-collection")
    assert "september11" in str(excinfo.value)


def test_a_collection_can_be_registered_and_removed() -> None:
    collection = BaseCollection(id="temp_collection", name="Temporary")
    register_collection(collection)
    try:
        assert get_collection("temp_collection") is collection
    finally:
        unregister_collection("temp_collection")
    with pytest.raises(UnknownCollectionError):
        get_collection("temp_collection")


def test_duplicate_registration_is_rejected() -> None:
    collection = BaseCollection(id="dupe_collection", name="Dupe")
    register_collection(collection)
    try:
        with pytest.raises(ValueError):
            register_collection(BaseCollection(id="dupe_collection", name="Other"))
    finally:
        unregister_collection("dupe_collection")


def test_base_collection_needs_no_configuration() -> None:
    """A collection with no ontology and no registry still works generically."""

    collection = BaseCollection(id="bare", name="Bare")
    assert collection.sources() == []
    assert collection.classify_record(_item(media_type_raw="photograph")) == "photo"
    assert collection.source_value("anything") == pytest.approx(0.65)


def test_september11_ontology_extends_rather_than_replaces_generic_types() -> None:
    ontology = get_collection("september11").ontology
    # Engine generics survive.
    assert "person" in ontology.entity_types
    assert "unit" in ontology.entity_types
    # Collection extension is present.
    assert "responder_unit" in ontology.entity_types
    with pytest.raises(OntologyError):
        ontology.check_entity_type("unicorn")


def test_september11_registry_moved_into_the_collection() -> None:
    collection = get_collection("september11")
    ids = {entry.id for entry in collection.sources()}
    assert "september11-digital-archive" in ids
    assert "nist-wtc-disaster-repository" in ids


def test_demo_collection_has_its_own_ontology_and_sources() -> None:
    collection = get_collection("demo_history")
    assert "mill" in collection.ontology.entity_types
    assert "fire" in collection.ontology.event_types
    assert {entry.id for entry in collection.sources()} == {
        "demo-borough-record-office",
        "demo-oral-history-project",
        "demo-photo-collection",
    }
    # The demo ontology must not inherit September 11 vocabulary.
    assert "responder_unit" not in collection.ontology.entity_types
