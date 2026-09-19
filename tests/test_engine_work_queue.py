"""The queue engine must work for a collection it has never heard of."""

from __future__ import annotations

import pytest

from archive.models import SourceItem
from archive.work_queue import build_work_queue as legacy_build_work_queue
from historical_engine.collection import BaseCollection, CollectionHooks
from historical_engine.collection_registry import get_collection
from historical_engine.work_queue import build_rights_queue, build_work_queue, tasks_for_item


def _item(**kwargs) -> SourceItem:
    payload = {
        "id": "item:1",
        "source_id": "unheard-of-source",
        "source_item_id": "1",
        "source_url": "https://example.test/1",
    }
    payload.update(kwargs)
    return SourceItem(**payload)


def test_generic_collection_produces_tasks() -> None:
    collection = BaseCollection(id="generic", name="Generic")
    tasks = tasks_for_item(_item(title_raw="A photograph", media_type_raw="photo"), collection)
    by_type = {task.task_type: task for task in tasks}

    assert "resolve_time" in by_type
    assert by_type["resolve_location"].expected_claim_kind == "capture_location"
    assert by_type["resolve_location"].record_role == "photo"
    assert by_type["resolve_time"].collection_id == "generic"


def test_rights_tasks_stay_out_of_the_research_queue() -> None:
    collection = BaseCollection(id="generic", name="Generic")
    records = [_item(media_type_raw="photo")]
    assert all(task.task_type != "resolve_rights" for task in build_work_queue(records, collection))
    rights = build_rights_queue(records, collection)
    assert [task.task_type for task in rights] == ["resolve_rights"]


def test_source_value_changes_priority_without_engine_changes() -> None:
    low = BaseCollection(id="low", name="Low", source_values={"unheard-of-source": 0.1})
    high = BaseCollection(id="high", name="High", source_values={"unheard-of-source": 1.0})
    item = _item(media_type_raw="photo")
    low_task = tasks_for_item(item, low)[0]
    high_task = tasks_for_item(item, high)[0]
    assert high_task.priority > low_task.priority


def test_collection_hook_suppresses_a_resolved_document_time() -> None:
    """The engine asks the collection, rather than knowing about FDNY titles."""

    without = BaseCollection(id="plain", name="Plain")
    with_hook = BaseCollection(
        id="hooked",
        name="Hooked",
        hooks=CollectionHooks(has_deterministic_time=lambda record: True),
    )
    item = _item(media_type_raw="document", title_raw="Some report")

    assert any(task.task_type == "resolve_time" for task in tasks_for_item(item, without))
    assert not any(task.task_type == "resolve_time" for task in tasks_for_item(item, with_hook))


def test_sensitive_policy_flags_human_review() -> None:
    september11 = get_collection("september11")
    testimony = _item(
        source_id="september-11-digital-archive",
        metadata_raw={"collection_id": 267},
        title_raw="Interview",
    )
    photo = _item(source_id="archdisk-911-photo-map", title_raw="Photo")

    assert all(task.requires_human_review for task in tasks_for_item(testimony, september11))
    assert not any(task.requires_human_review for task in tasks_for_item(photo, september11))


def test_legacy_api_matches_the_explicit_collection_call() -> None:
    """`archive.work_queue` with no collection == the september11 collection."""

    records = [
        _item(id="a", source_id="archdisk-911-photo-map"),
        _item(id="b", source_id="internet-archive-understanding-911"),
        _item(id="c", media_type_raw="document", title_raw="Incident Action Plan: 9/14/01"),
    ]
    explicit = build_work_queue(records, get_collection("september11"))
    legacy = legacy_build_work_queue(records)
    assert [task.to_dict() for task in legacy] == [task.to_dict() for task in explicit]


def test_demo_collection_runs_through_the_same_queue() -> None:
    from evidence_collections.demo_history.pipeline import load_records

    collection = get_collection("demo_history")
    tasks = build_work_queue(load_records(), collection)
    assert tasks
    assert {task.collection_id for task in tasks} == {"demo_history"}
    roles = {task.record_role for task in tasks}
    assert {"document", "testimony", "photo"} & roles


@pytest.mark.parametrize("collection_id", ["september11", "demo_history"])
def test_queue_construction_needs_no_core_changes(collection_id: str) -> None:
    """Same engine call, two unrelated corpora."""

    collection = get_collection(collection_id)
    # The engine contract does not require a record to use a registered source.
    # A synthetic source keeps this collection-agnostic test independent of set/hash order
    # and of collection-specific deterministic-source rules.
    item = _item(source_id=f"{collection_id}-synthetic-source", media_type_raw="photo")
    tasks = tasks_for_item(item, collection)
    assert tasks and all(task.collection_id == collection_id for task in tasks)
