from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


def load_decisions(path: Path | str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid decision JSONL at {path}:{line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"expected decision object at {path}:{line_number}")
            rows.append(payload)
    return rows


def _band(confidence: float) -> str:
    if confidence >= 0.95:
        return "0.95-1.00"
    if confidence >= 0.85:
        return "0.85-0.94"
    if confidence >= 0.70:
        return "0.70-0.84"
    if confidence >= 0.40:
        return "0.40-0.69"
    return "0.00-0.39"


def analyze_calibration(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    answer_counts: Counter[str] = Counter()
    question_counts: Counter[str] = Counter()
    routing_counts: Counter[str] = Counter()
    confidence_bands: Counter[str] = Counter()
    proposal_counts: Counter[str] = Counter()

    confidences: list[float] = []
    review_rows: list[dict[str, Any]] = []

    for row in decisions:
        answer = str(row.get("answer") or "unknown")
        question = str(row.get("question") or "unknown")
        confidence = float(row.get("confidence") or 0.0)
        routing = row.get("routing") or {}
        routing_decision = str(routing.get("decision") or "unknown")
        proposal_id = row.get("proposal_id")

        answer_counts[answer] += 1
        question_counts[question] += 1
        routing_counts[routing_decision] += 1
        confidence_bands[_band(confidence)] += 1
        proposal_counts["with_proposal" if proposal_id else "without_proposal"] += 1
        confidences.append(confidence)

        context = row.get("context") or {}
        heuristic_score = context.get("candidate_score")
        if (
            routing_decision in {"human_review", "weak_candidate"}
            or 0.40 <= confidence < 0.95
        ):
            review_rows.append(
                {
                    "question": question,
                    "subject_id": row.get("subject_id"),
                    "object_id": row.get("object_id"),
                    "answer": answer,
                    "confidence": confidence,
                    "routing_decision": routing_decision,
                    "candidate_score": heuristic_score,
                    "subject_name": context.get("subject_name"),
                    "object_name": context.get("object_name"),
                    "proposal_id": proposal_id,
                }
            )

    review_rows.sort(key=lambda row: (float(row["confidence"]), str(row["question"])))

    return {
        "decisions": len(decisions),
        "mean_confidence": round(mean(confidences), 4) if confidences else 0.0,
        "minimum_confidence": round(min(confidences), 4) if confidences else 0.0,
        "maximum_confidence": round(max(confidences), 4) if confidences else 0.0,
        "question_counts": dict(sorted(question_counts.items())),
        "answer_counts": dict(sorted(answer_counts.items())),
        "routing_counts": dict(sorted(routing_counts.items())),
        "confidence_bands": {
            band: confidence_bands.get(band, 0)
            for band in ("0.95-1.00", "0.85-0.94", "0.70-0.84", "0.40-0.69", "0.00-0.39")
        },
        "proposal_counts": dict(sorted(proposal_counts.items())),
        "manual_review_priority": review_rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Jev Calibration Report",
        "",
        f"- Decisions: **{report['decisions']}**",
        f"- Mean confidence: **{report['mean_confidence']:.3f}**",
        f"- Confidence range: **{report['minimum_confidence']:.3f}–{report['maximum_confidence']:.3f}**",
        "",
        "## Questions",
        "",
    ]
    for key, value in report["question_counts"].items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Answers", ""])
    for key, value in report["answer_counts"].items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Confidence bands", ""])
    for key, value in report["confidence_bands"].items():
        lines.append(f"- **{key}**: {value}")

    lines.extend(["", "## Routing", ""])
    for key, value in report["routing_counts"].items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Manual-review priority", ""])
    priority = report["manual_review_priority"]
    if not priority:
        lines.append("- No medium/ambiguous cases in this batch.")
    else:
        for row in priority[:50]:
            subject = row.get("subject_name") or row.get("subject_id")
            object_name = row.get("object_name") or row.get("object_id")
            lines.append(
                f"- **{row['question']}** — {subject} ↔ {object_name}: "
                f"`{row['answer']}`, confidence {row['confidence']:.3f}, "
                f"routing `{row['routing_decision']}`"
            )

    lines.append("")
    return "\n".join(lines)


def write_calibration_report(
    decisions_path: Path | str,
    *,
    json_output: Path | str | None = None,
    markdown_output: Path | str | None = None,
) -> dict[str, Any]:
    report = analyze_calibration(load_decisions(decisions_path))

    if json_output is not None:
        path = Path(json_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if markdown_output is not None:
        path = Path(markdown_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(report), encoding="utf-8")

    return report
