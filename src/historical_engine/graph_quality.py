from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_PLACEHOLDERS = frozenset(
    {
        "",
        "unknown",
        "not provided",
        "not provided.",
        "none selected",
        "n/a",
        "na",
        "none",
        "null",
        "undefined",
    }
)


def _casefold(value: Any) -> str:
    return str(value or "").strip().casefold()


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def analyze_graph_quality(
    database: Path | str,
    *,
    placeholders: Iterable[str] = DEFAULT_PLACEHOLDERS,
    high_degree_threshold: int = 20,
) -> dict[str, Any]:
    """Inspect a materialized evidence graph for common quality failures.

    This is intentionally descriptive rather than corrective. It reports likely
    cleanup/review pressure without silently merging, deleting, or verifying any
    historical assertion.
    """

    path = Path(database)
    placeholder_set = {_casefold(value) for value in placeholders}

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        source_records = _table_count(connection, "source_records")
        entities = _table_count(connection, "entities")
        events = _table_count(connection, "events")
        relationships = _table_count(connection, "relationships")

        source_counts = {
            row["source_id"]: int(row["count"])
            for row in connection.execute(
                "SELECT source_id, COUNT(*) AS count FROM source_records GROUP BY source_id ORDER BY source_id"
            )
        }

        predicate_counts = {
            row["predicate"]: int(row["count"])
            for row in connection.execute(
                "SELECT predicate, COUNT(*) AS count FROM relationships GROUP BY predicate ORDER BY count DESC, predicate"
            )
        }

        assertion_counts = {
            row["assertion_level"]: int(row["count"])
            for row in connection.execute(
                "SELECT assertion_level, COUNT(*) AS count FROM relationships "
                "GROUP BY assertion_level ORDER BY count DESC, assertion_level"
            )
        }

        review_counts = {
            row["status"]: int(row["count"])
            for row in connection.execute(
                "SELECT status, COUNT(*) AS count FROM relationships GROUP BY status ORDER BY status"
            )
        }

        entity_rows = connection.execute(
            "SELECT entity_id, entity_type, canonical_name, attributes_json FROM entities"
        ).fetchall()

        placeholder_entities: list[dict[str, str]] = []
        names: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
        for row in entity_rows:
            normalized = _casefold(row["canonical_name"])
            if normalized in placeholder_set:
                placeholder_entities.append(
                    {
                        "entity_id": row["entity_id"],
                        "entity_type": row["entity_type"],
                        "canonical_name": row["canonical_name"],
                    }
                )
            if normalized:
                names[(row["entity_type"], normalized)].append(row["entity_id"])

        duplicate_name_groups = [
            {
                "entity_type": entity_type,
                "normalized_name": normalized_name,
                "entity_ids": sorted(ids),
                "count": len(ids),
            }
            for (entity_type, normalized_name), ids in names.items()
            if len(ids) > 1
        ]
        duplicate_name_groups.sort(
            key=lambda row: (-int(row["count"]), row["entity_type"], row["normalized_name"])
        )

        degree: Counter[tuple[str, str]] = Counter()
        for row in connection.execute(
            "SELECT subject_type, subject_id, object_type, object_id FROM relationships"
        ):
            degree[(row["subject_type"], row["subject_id"])] += 1
            degree[(row["object_type"], row["object_id"])] += 1

        isolated_entities = [
            {
                "entity_id": row["entity_id"],
                "entity_type": row["entity_type"],
                "canonical_name": row["canonical_name"],
            }
            for row in entity_rows
            if degree[(row["entity_type"], row["entity_id"])] == 0
        ]

        event_rows = connection.execute(
            "SELECT event_id, name, event_type, start_time, end_time, time_precision FROM events"
        ).fetchall()
        isolated_events = [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "name": row["name"],
            }
            for row in event_rows
            if degree[("event", row["event_id"])] == 0
        ]

        missing_event_start_times = [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "name": row["name"],
            }
            for row in event_rows
            if not row["start_time"]
        ]

        invalid_time_ranges = [
            {
                "event_id": row["event_id"],
                "start_time": row["start_time"],
                "end_time": row["end_time"],
            }
            for row in event_rows
            if row["start_time"] and row["end_time"] and row["end_time"] < row["start_time"]
        ]

        endpoint_labels: dict[tuple[str, str], str] = {}
        for row in entity_rows:
            endpoint_labels[(row["entity_type"], row["entity_id"])] = row["canonical_name"]
        for row in event_rows:
            endpoint_labels[("event", row["event_id"])] = row["name"]

        high_degree_nodes = [
            {
                "node_type": node_type,
                "node_id": node_id,
                "label": endpoint_labels.get((node_type, node_id)),
                "degree": count,
            }
            for (node_type, node_id), count in degree.items()
            if count >= high_degree_threshold
        ]
        high_degree_nodes.sort(key=lambda row: (-int(row["degree"]), row["node_type"], row["node_id"]))

        dangling_endpoints: list[dict[str, str]] = []
        known = set(endpoint_labels)
        for row in connection.execute(
            "SELECT relationship_id, subject_type, subject_id, object_type, object_id FROM relationships"
        ):
            for side in ("subject", "object"):
                node = (row[f"{side}_type"], row[f"{side}_id"])
                if node not in known:
                    dangling_endpoints.append(
                        {
                            "relationship_id": row["relationship_id"],
                            "side": side,
                            "node_type": node[0],
                            "node_id": node[1],
                        }
                    )

        node_count = entities + events
        relationship_density = relationships / node_count if node_count else 0.0

        warnings: list[dict[str, Any]] = []
        if placeholder_entities:
            warnings.append(
                {
                    "code": "placeholder_entities",
                    "severity": "high",
                    "count": len(placeholder_entities),
                    "message": "Placeholder text leaked into canonical graph entities.",
                }
            )
        if duplicate_name_groups:
            warnings.append(
                {
                    "code": "duplicate_entity_names",
                    "severity": "medium",
                    "count": len(duplicate_name_groups),
                    "message": "Multiple canonical entities share the same normalized name/type; entity resolution may be needed.",
                }
            )
        if dangling_endpoints:
            warnings.append(
                {
                    "code": "dangling_relationship_endpoints",
                    "severity": "high",
                    "count": len(dangling_endpoints),
                    "message": "Relationships reference nodes that are not present in the graph tables.",
                }
            )
        if isolated_entities or isolated_events:
            warnings.append(
                {
                    "code": "isolated_nodes",
                    "severity": "low",
                    "count": len(isolated_entities) + len(isolated_events),
                    "message": "Some derived graph nodes have no relationships.",
                }
            )
        if missing_event_start_times:
            warnings.append(
                {
                    "code": "missing_event_times",
                    "severity": "medium",
                    "count": len(missing_event_start_times),
                    "message": "Some events lack a parseable start time.",
                }
            )
        if invalid_time_ranges:
            warnings.append(
                {
                    "code": "invalid_event_time_ranges",
                    "severity": "high",
                    "count": len(invalid_time_ranges),
                    "message": "One or more event end times precede start times.",
                }
            )

        return {
            "database": str(path),
            "counts": {
                "source_records": source_records,
                "entities": entities,
                "events": events,
                "relationships": relationships,
                "nodes": node_count,
            },
            "source_counts": source_counts,
            "predicate_counts": predicate_counts,
            "assertion_level_counts": assertion_counts,
            "relationship_review_status_counts": review_counts,
            "relationship_density_per_node": round(relationship_density, 4),
            "duplicate_entity_name_groups": duplicate_name_groups,
            "placeholder_entities": placeholder_entities,
            "isolated_entities": isolated_entities,
            "isolated_events": isolated_events,
            "missing_event_start_times": missing_event_start_times,
            "invalid_event_time_ranges": invalid_time_ranges,
            "dangling_relationship_endpoints": dangling_endpoints,
            "high_degree_threshold": high_degree_threshold,
            "high_degree_nodes": high_degree_nodes,
            "warnings": warnings,
        }
    finally:
        connection.close()


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        "# Evidence Graph Quality Report",
        "",
        f"- Source records: **{counts['source_records']}**",
        f"- Entities: **{counts['entities']}**",
        f"- Events: **{counts['events']}**",
        f"- Relationships: **{counts['relationships']}**",
        f"- Relationship density per node: **{report['relationship_density_per_node']}**",
        "",
        "## Relationship predicates",
        "",
    ]
    if report["predicate_counts"]:
        for predicate, count in report["predicate_counts"].items():
            lines.append(f"- {predicate}: {count}")
    else:
        lines.append("- No relationships materialized.")

    lines.extend(["", "## Warnings", ""])
    if report["warnings"]:
        for warning in report["warnings"]:
            lines.append(
                f"- **{warning['severity'].upper()}** {warning['code']} "
                f"({warning['count']}): {warning['message']}"
            )
    else:
        lines.append("- No automatic quality warnings.")

    lines.extend(["", "## High-degree nodes", ""])
    if report["high_degree_nodes"]:
        for node in report["high_degree_nodes"][:25]:
            label = node.get("label") or node["node_id"]
            lines.append(
                f"- {node['node_type']} **{label}** — degree {node['degree']}"
            )
    else:
        lines.append(
            f"- No nodes at or above degree {report['high_degree_threshold']}."
        )

    lines.extend(["", "## Duplicate canonical-name pressure", ""])
    if report["duplicate_entity_name_groups"]:
        for group in report["duplicate_entity_name_groups"][:25]:
            lines.append(
                f"- {group['entity_type']} **{group['normalized_name']}** — "
                f"{group['count']} canonical nodes"
            )
    else:
        lines.append("- No duplicate canonical-name/type groups detected.")

    lines.append("")
    return "\n".join(lines)


def write_report(
    database: Path | str,
    *,
    json_output: Path | str | None = None,
    markdown_output: Path | str | None = None,
    high_degree_threshold: int = 20,
) -> dict[str, Any]:
    report = analyze_graph_quality(
        database,
        high_degree_threshold=high_degree_threshold,
    )
    if json_output is not None:
        path = Path(json_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if markdown_output is not None:
        path = Path(markdown_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(report), encoding="utf-8")
    return report
