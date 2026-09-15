from __future__ import annotations

from archive.models import SourceItem
from archive.work_queue import build_work_queue, tasks_for_item


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
