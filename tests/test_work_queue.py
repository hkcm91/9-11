from __future__ import annotations

from archive.models import SourceItem
from archive.work_queue import build_rights_queue, build_work_queue, tasks_for_item


def test_missing_time_and_location_create_specific_tasks() -> None:
    item = SourceItem(
        id="item:1",
        source_id="september-11-digital-archive",
        source_item_id="1",
        source_url="https://example.test/1",
        title_raw="Known title",
        creator_raw="Known creator",
    )
    tasks = tasks_for_item(item)
    task_types = {task.task_type for task in tasks}

    assert "resolve_time" in task_types
    assert "resolve_location" in task_types
    assert "resolve_creator" not in task_types
    assert "resolve_rights" not in task_types


def test_visual_location_task_requests_capture_location() -> None:
    item = SourceItem(
        id="photo:1",
        source_id="source",
        source_item_id="1",
        source_url="https://example.test/1",
        title_raw="Photo",
        media_type_raw="photo",
    )
    location_task = next(task for task in tasks_for_item(item) if task.task_type == "resolve_location")
    assert location_task.record_role == "photo"
    assert location_task.expected_claim_kind == "capture_location"
    assert "camera capture location" in location_task.instructions


def test_fdny_plan_uses_deterministic_coverage_date_and_skips_geolocation() -> None:
    item = SourceItem(
        id="plan:1",
        source_id="september-11-digital-archive",
        source_item_id="1751",
        source_url="https://911digitalarchive.org/items/show/1751",
        title_raw="Incident Action Plan: 10/16/01 - 10/17/01",
        collection_raw="11",
        metadata_raw={"collection_id": 11},
    )
    task_types = {task.task_type for task in tasks_for_item(item)}
    assert "resolve_time" not in task_types
    assert "resolve_location" not in task_types
    assert "classify_media" not in task_types
    assert "resolve_creator" in task_types


def test_repository_entry_does_not_generate_historical_research_tasks() -> None:
    item = SourceItem(
        id="nist:repo",
        source_id="nist-wtc-disaster-repository",
        source_item_id="repo",
        source_url="https://example.test/repo",
        title_raw="Original Video from Tapes",
        media_type_raw="repository_entry",
    )
    task_types = {task.task_type for task in tasks_for_item(item)}
    assert "resolve_time" not in task_types
    assert "resolve_location" not in task_types
    assert "resolve_creator" not in task_types


def test_tv_archive_item_is_broadcast_anchor_not_camera_geolocation_task() -> None:
    item = SourceItem(
        id="internet-archive-understanding-911:tv-1",
        source_id="internet-archive-understanding-911",
        source_item_id="tv-1",
        source_url="https://archive.org/details/tv-1",
        title_raw="Television coverage",
        creator_raw="NHK",
        date_raw="2001-09-11",
        media_type_raw="movies",
        metadata_raw={"start_time": "2001-09-11 12:00:00", "stop_time": "2001-09-11 12:30:00"},
    )

    tasks = tasks_for_item(item)
    assert {task.record_role for task in tasks} <= {"broadcast"}
    assert "resolve_location" not in {task.task_type for task in tasks}
    assert "classify_media" not in {task.task_type for task in tasks}


def test_known_911da_collection_role_suppresses_generic_classification() -> None:
    voices = SourceItem(
        id="voice:1",
        source_id="september-11-digital-archive",
        source_item_id="1",
        source_url="https://example.test/voice/1",
        title_raw="V001 Jane Doe.mov",
        metadata_raw={"collection_id": 267},
    )
    sonic = SourceItem(
        id="audio:1",
        source_id="september-11-digital-archive",
        source_item_id="2",
        source_url="https://example.test/audio/1",
        title_raw="Audio record",
        metadata_raw={"collection_id": 266},
    )

    voice_tasks = tasks_for_item(voices)
    sonic_tasks = tasks_for_item(sonic)

    assert {task.record_role for task in voice_tasks} <= {"testimony"}
    assert {task.record_role for task in sonic_tasks} <= {"audio"}
    assert "classify_media" not in {task.task_type for task in voice_tasks}
    assert "classify_media" not in {task.task_type for task in sonic_tasks}


def test_rights_clearance_is_separate_from_default_research_queue() -> None:
    item = SourceItem(
        id="photo:rights",
        source_id="source",
        source_item_id="rights",
        source_url="https://example.test/rights",
        title_raw="Photo",
        media_type_raw="photo",
    )

    research_types = {task.task_type for task in tasks_for_item(item)}
    rights_tasks = build_rights_queue([item])

    assert "resolve_rights" not in research_types
    assert len(rights_tasks) == 1
    assert rights_tasks[0].task_type == "resolve_rights"


def test_task_ids_are_stable() -> None:
    item = SourceItem(
        id="item:1",
        source_id="source",
        source_item_id="1",
        source_url="https://example.test/1",
    )
    first = {task.task_type: task.task_id for task in tasks_for_item(item)}
    second = {task.task_type: task.task_id for task in tasks_for_item(item)}
    assert first == second


def test_queue_is_priority_sorted() -> None:
    sparse = SourceItem(
        id="sparse",
        source_id="september-11-digital-archive",
        source_item_id="1",
        source_url="https://example.test/1",
        title_raw="Title",
    )
    rich = SourceItem(
        id="rich",
        source_id="september-11-digital-archive",
        source_item_id="2",
        source_url="https://example.test/2",
        title_raw="Title",
        creator_raw="Creator",
        date_raw="2001-09-11",
        location_raw="NYC",
        rights_raw="Known",
        description_raw="Description",
        collection_raw="Collection",
        media_type_raw="photo",
    )

    tasks = build_work_queue([rich, sparse])
    assert tasks
    assert tasks[0].item_id == "sparse"
