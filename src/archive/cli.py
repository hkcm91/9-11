from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from archive.adapters import (
    ArcGisPhotoMapAdapter,
    InternetArchiveAdapter,
    NistOrganizedMediaAdapter,
    NistWtcRepositoryAdapter,
    September11DigitalArchiveAdapter,
)
from archive.collections_compat import DEFAULT_COLLECTION_ID, resolve_collection
from archive.corpus import load_jsonl, reconcile_source_snapshots
from archive.adapters.nist_organized import nist_inventory_report
from archive.dedupe import find_candidates
from archive.derived import (
    derive_entity_claims,
    derive_spatial_claims,
    derive_temporal_claims,
    serialize_entity_claim,
    serialize_spatial_claim,
    serialize_temporal_claim,
)
from archive.profiling import profile_records
from archive.quality import prioritize_records
from archive.registry import enabled_sources
from archive.store import ArchiveStore
from archive.work_queue import build_rights_queue, build_work_queue


def _add_output_args(parser: argparse.ArgumentParser, *, default_delay: float) -> None:
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=default_delay)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archive-ingest")
    parser.add_argument(
        "--collection",
        default=None,
        help=(
            "Collection to operate on (for example september11 or demo_history). "
            f"TRANSITIONAL: defaults to '{DEFAULT_COLLECTION_ID}' so existing commands "
            "keep working; set HISTORICAL_ENGINE_COLLECTION to change the default."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_collections = subparsers.add_parser(
        "list-collections", help="List the collections registered with the engine"
    )
    list_collections.add_argument("--verbose", action="store_true")

    sample_911da = subparsers.add_parser("sample-911da", help="Sample metadata from the September 11 Digital Archive")
    _add_output_args(sample_911da, default_delay=1.0)
    sample_911da.add_argument("--collection", dest="source_collection_id", type=int, default=None)
    sample_911da.add_argument("--details", action="store_true", help="Enrich each record with Dublin Core XML metadata")

    sample_ia = subparsers.add_parser("sample-internet-archive", help="Sample Internet Archive Understanding 9/11 metadata")
    _add_output_args(sample_ia, default_delay=0.5)
    sample_ia.add_argument("--collection", dest="ia_collection", default="911")
    sample_ia.add_argument("--details", action="store_true", help="Fetch full item metadata and summarize files")

    sample_nist = subparsers.add_parser("sample-nist", help="Inventory public NIST WTC repository entry points")
    sample_nist.add_argument("--output", type=Path, required=True)
    sample_nist.add_argument("--delay", type=float, default=0.5)

    sample_nist_organized = subparsers.add_parser(
        "sample-nist-organized",
        help="Sample asset metadata from NIST's public organized photo/video hierarchy",
    )
    _add_output_args(sample_nist_organized, default_delay=0.25)
    sample_nist_organized.add_argument("--folder-id", default=None)
    sample_nist_organized.add_argument(
        "--media-type",
        choices=("both", "photo", "video"),
        default="both",
        help="Balance the limit across both media families, or select one family",
    )

    inventory_nist_organized = subparsers.add_parser(
        "inventory-nist-organized",
        help="Inventory the complete public NIST photo/video hierarchy and report claim coverage",
    )
    inventory_nist_organized.add_argument("--output", type=Path, required=True)
    inventory_nist_organized.add_argument("--report", type=Path, required=True)
    inventory_nist_organized.add_argument("--folder-id", default=None)
    inventory_nist_organized.add_argument("--delay", type=float, default=0.2)
    inventory_nist_organized.add_argument("--max-attempts", type=int, default=3)
    inventory_nist_organized.add_argument(
        "--media-type", choices=("both", "photo", "video"), default="both"
    )

    import_nist_organized = subparsers.add_parser(
        "import-nist-organized",
        help="Import a NIST organized-media CSV, JSON, JSONL, or NDJSON manifest",
    )
    import_nist_organized.add_argument("input", type=Path)
    import_nist_organized.add_argument("--output", type=Path, required=True)
    import_nist_organized.add_argument("--limit", type=int, default=None)

    import_wikileaks_plusd = subparsers.add_parser(
        "import-wikileaks-plusd",
        help="Import Cablegate/PlusD CSV, JSON, JSONL, or NDJSON records",
    )
    import_wikileaks_plusd.add_argument("input", type=Path)
    import_wikileaks_plusd.add_argument("--output", type=Path, required=True)
    import_wikileaks_plusd.add_argument("--limit", type=int, default=None)

    import_wikileaks_war = subparsers.add_parser(
        "import-wikileaks-war-diaries",
        help="Import Iraq/Afghan War Diaries CSV, JSON, JSONL, or NDJSON records",
    )
    import_wikileaks_war.add_argument("input", type=Path)
    import_wikileaks_war.add_argument("--output", type=Path, required=True)
    import_wikileaks_war.add_argument("--limit", type=int, default=None)

    fetch_wikileaks_real = subparsers.add_parser(
        "fetch-wikileaks-real-samples",
        help="Fetch bounded real Cablegate and Iraq War Logs CSV samples from public mirrors",
    )
    fetch_wikileaks_real.add_argument("--output-dir", type=Path, required=True)
    fetch_wikileaks_real.add_argument("--limit", type=int, default=100)
    fetch_wikileaks_real.add_argument("--timeout", type=float, default=60.0)
    fetch_wikileaks_real.add_argument("--manifest", type=Path, default=None)

    sample_photo_map = subparsers.add_parser("sample-photo-map", help="Sample geolocated metadata from the public archDisk ArcGIS map")
    _add_output_args(sample_photo_map, default_delay=0.25)
    sample_photo_map.add_argument("--app-id", default="1b7d4d22866b445881b181614e25d4d4")

    sources = subparsers.add_parser("list-sources", help="List the active collection's enabled sources")
    sources.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Registry file to read instead of the collection's own sources.yaml",
    )

    profile = subparsers.add_parser("profile-jsonl", help="Profile metadata coverage in one or more JSONL corpora")
    profile.add_argument("inputs", nargs="+", type=Path)
    profile.add_argument("--output", type=Path, default=None)

    dedupe = subparsers.add_parser("dedupe-jsonl", help="Propose likely duplicate records without merging them")
    dedupe.add_argument("inputs", nargs="+", type=Path)
    dedupe.add_argument("--threshold", type=float, default=0.86)
    dedupe.add_argument(
        "--include-same-source",
        action="store_true",
        help="Also run the stricter duplicate pass within one custodial source",
    )
    dedupe.add_argument("--output", type=Path, required=True)

    prioritize = subparsers.add_parser("prioritize-jsonl", help="Rank records for metadata enrichment work")
    prioritize.add_argument("inputs", nargs="+", type=Path)
    prioritize.add_argument("--output", type=Path, required=True)

    temporal_claims = subparsers.add_parser("derive-temporal-claims", help="Create deterministic evidence-backed temporal claims")
    temporal_claims.add_argument("inputs", nargs="+", type=Path)
    temporal_claims.add_argument("--output", type=Path, required=True)

    spatial_claims = subparsers.add_parser("derive-spatial-claims", help="Create provenance-backed spatial claims from structured geometry")
    spatial_claims.add_argument("inputs", nargs="+", type=Path)
    spatial_claims.add_argument("--output", type=Path, required=True)

    entity_claims = subparsers.add_parser("derive-entity-claims", help="Create evidence-backed person/organization references")
    entity_claims.add_argument("inputs", nargs="+", type=Path)
    entity_claims.add_argument("--output", type=Path, required=True)

    work_queue = subparsers.add_parser("build-work-queue", help="Create evidence-focused historical research tasks")
    work_queue.add_argument("inputs", nargs="+", type=Path)
    work_queue.add_argument("--output", type=Path, required=True)

    rights_queue = subparsers.add_parser("build-rights-queue", help="Create separate publication/rights-clearance tasks")
    rights_queue.add_argument("inputs", nargs="+", type=Path)
    rights_queue.add_argument("--output", type=Path, required=True)

    graph = subparsers.add_parser(
        "build-graph",
        help="Materialize a collection's deterministic evidence graph into SQLite",
    )
    graph.add_argument("inputs", nargs="+", type=Path)
    graph.add_argument("--database", type=Path, required=True)
    graph.add_argument("--stats-output", type=Path, default=None)

    graph_quality = subparsers.add_parser(
        "analyze-graph-quality",
        help="Audit a materialized evidence graph for structural/noise problems",
    )
    graph_quality.add_argument("--database", type=Path, required=True)
    graph_quality.add_argument("--json-output", type=Path, default=None)
    graph_quality.add_argument("--markdown-output", type=Path, default=None)
    graph_quality.add_argument("--high-degree-threshold", type=int, default=20)

    jev_config = subparsers.add_parser(
        "jev-config-check",
        help="Check whether TypeSafe/Jev credentials and endpoint configuration are available without printing secrets",
    )
    jev_config.add_argument("--dotenv", type=Path, default=Path(".env"))

    resolution_candidates = subparsers.add_parser(
        "build-resolution-candidates",
        help="Generate reviewable same-entity and same-event decision requests from a graph",
    )
    resolution_candidates.add_argument("--database", type=Path, required=True)
    resolution_candidates.add_argument("--output", type=Path, required=True)
    resolution_candidates.add_argument("--max-entity-pairs", type=int, default=500)
    resolution_candidates.add_argument("--max-event-pairs", type=int, default=500)

    jev_batch = subparsers.add_parser(
        "run-jev-decisions",
        help="Run a DecisionRequest JSONL queue through TypeSafe Jev and emit proposal-only outputs",
    )
    jev_batch.add_argument("input", type=Path)
    jev_batch.add_argument("--output", type=Path, required=True)
    jev_batch.add_argument("--proposal-output", type=Path, default=None)
    jev_batch.add_argument("--dotenv", type=Path, default=Path(".env"))
    jev_batch.add_argument("--timeout", type=float, default=30.0)
    jev_batch.add_argument("--agent-version", default="jev-http-v1")
    jev_batch.add_argument("--limit", type=int, default=None)

    jev_calibration = subparsers.add_parser(
        "analyze-jev-calibration",
        help="Summarize confidence, routing, and review pressure from Jev decision JSONL",
    )
    jev_calibration.add_argument("input", type=Path)
    jev_calibration.add_argument("--json-output", type=Path, default=None)
    jev_calibration.add_argument("--markdown-output", type=Path, default=None)

    demo = subparsers.add_parser(
        "run-demo-pipeline",
        help="Run the synthetic demo_history corpus end-to-end through the generic engine",
    )
    demo.add_argument("--database", type=Path, required=True)
    demo.add_argument("--stats-output", type=Path, default=None)

    store = subparsers.add_parser("build-store", help="Materialize source observations and claims into SQLite")
    store.add_argument("--database", type=Path, required=True)
    store.add_argument("--records", nargs="+", type=Path, required=True)
    store.add_argument("--temporal", type=Path, default=None)
    store.add_argument("--spatial", type=Path, default=None)
    store.add_argument("--entities", type=Path, default=None)
    store.add_argument("--stats-output", type=Path, default=None)
    return parser


def _write_jsonl(output: Path, records: list, serializer) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(serializer(record), ensure_ascii=False))
            handle.write("\n")


def _load_many(paths: list[Path]):
    records = []
    for path in paths:
        records.extend(load_jsonl(path))
    return reconcile_source_snapshots(records)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    collection = resolve_collection(getattr(args, "collection", None))

    if args.command == "list-collections":
        from historical_engine.collection_registry import iter_collections

        for entry in iter_collections():
            marker = "*" if entry.id == collection.id else " "
            print(f"{marker} {entry.id:16} {entry.name}")
            if args.verbose:
                print(f"    ontology v{entry.ontology.version}, {len(entry.sources())} enabled sources")
                print(f"    {entry.description}")
        return 0

    if args.command == "sample-911da":
        adapter = September11DigitalArchiveAdapter(request_delay_s=args.delay)
        records = adapter.sample(limit=args.limit, collection_id=args.source_collection_id, enrich=args.details)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} metadata records to {args.output}")
        return 0

    if args.command == "sample-internet-archive":
        adapter = InternetArchiveAdapter(collection=args.ia_collection, request_delay_s=args.delay)
        records = adapter.sample(limit=args.limit, enrich=args.details)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} metadata records to {args.output}")
        return 0

    if args.command == "sample-nist":
        adapter = NistWtcRepositoryAdapter(request_delay_s=args.delay)
        records = adapter.sample()
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} NIST repository records to {args.output}")
        return 0

    if args.command == "sample-nist-organized":
        kwargs = {"request_delay_s": args.delay}
        if args.folder_id:
            kwargs["folder_id"] = args.folder_id
        adapter = NistOrganizedMediaAdapter(**kwargs)
        media_type = None if args.media_type == "both" else args.media_type
        records = adapter.sample(limit=args.limit, media_type=media_type)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} NIST organized-media records to {args.output}")
        return 0

    if args.command == "inventory-nist-organized":
        kwargs = {"request_delay_s": args.delay, "max_attempts": args.max_attempts}
        if args.folder_id:
            kwargs["folder_id"] = args.folder_id
        adapter = NistOrganizedMediaAdapter(**kwargs)
        media_type = None if args.media_type == "both" else args.media_type
        records = adapter.inventory(media_type=media_type)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        report = nist_inventory_report(records)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {len(records)} NIST organized-media records and coverage report")
        return 0

    if args.command == "import-nist-organized":
        adapter = NistOrganizedMediaAdapter(request_delay_s=0)
        records = adapter.import_manifest(args.input, limit=args.limit)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} NIST organized-media records to {args.output}")
        return 0

    if args.command == "import-wikileaks-plusd":
        from evidence_collections.wikileaks.adapters import WikiLeaksPlusDAdapter

        adapter = WikiLeaksPlusDAdapter()
        records = adapter.import_file(args.input, limit=args.limit)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} WikiLeaks PlusD/Cablegate records to {args.output}")
        return 0

    if args.command == "import-wikileaks-war-diaries":
        from evidence_collections.wikileaks.adapters import WikiLeaksWarDiariesAdapter

        adapter = WikiLeaksWarDiariesAdapter()
        records = adapter.import_file(args.input, limit=args.limit)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} WikiLeaks War Diaries records to {args.output}")
        return 0

    if args.command == "fetch-wikileaks-real-samples":
        from evidence_collections.wikileaks.remote_sources import fetch_default_real_samples

        payload = fetch_default_real_samples(
            args.output_dir,
            limit=args.limit,
            timeout=args.timeout,
        )
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.manifest:
            args.manifest.parent.mkdir(parents=True, exist_ok=True)
            args.manifest.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0

    if args.command == "sample-photo-map":
        adapter = ArcGisPhotoMapAdapter(app_id=args.app_id, request_delay_s=args.delay)
        records = adapter.sample(limit=args.limit)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} geolocated photo-map records to {args.output}")
        return 0

    if args.command == "list-sources":
        sources = enabled_sources(args.registry) if args.registry else collection.sources()
        for source in sources:
            print(f"{source.priority.upper():8} {source.id:40} {source.name}")
        print(f"{len(sources)} enabled sources")
        return 0

    if args.command == "profile-jsonl":
        records = _load_many(args.inputs)
        payload = profile_records(records).to_dict()
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(f"wrote profile for {len(records)} reconciled records to {args.output}")
        else:
            print(rendered)
        return 0

    if args.command == "dedupe-jsonl":
        records = _load_many(args.inputs)
        candidates = find_candidates(
            records,
            threshold=args.threshold,
            include_same_source=args.include_same_source,
        )
        _write_jsonl(args.output, candidates, asdict)
        mode = "cross-source + strict same-source" if args.include_same_source else "cross-source"
        print(
            f"wrote {len(candidates)} {mode} duplicate candidates "
            f"from {len(records)} reconciled records to {args.output}"
        )
        return 0

    if args.command == "prioritize-jsonl":
        records = _load_many(args.inputs)
        priorities = prioritize_records(records, collection=collection)
        _write_jsonl(args.output, priorities, asdict)
        print(f"wrote {len(priorities)} enrichment priorities to {args.output}")
        return 0

    if args.command == "derive-temporal-claims":
        records = _load_many(args.inputs)
        claims = derive_temporal_claims(records, collection=collection)
        _write_jsonl(args.output, claims, serialize_temporal_claim)
        print(f"wrote {len(claims)} deterministic temporal claims to {args.output}")
        return 0

    if args.command == "derive-spatial-claims":
        records = _load_many(args.inputs)
        claims = derive_spatial_claims(records, collection=collection)
        _write_jsonl(args.output, claims, serialize_spatial_claim)
        print(f"wrote {len(claims)} provenance-backed spatial claims to {args.output}")
        return 0

    if args.command == "derive-entity-claims":
        records = _load_many(args.inputs)
        claims = derive_entity_claims(records, collection=collection)
        _write_jsonl(args.output, claims, serialize_entity_claim)
        print(f"wrote {len(claims)} entity-reference claims to {args.output}")
        return 0

    if args.command == "build-work-queue":
        records = _load_many(args.inputs)
        tasks = build_work_queue(records, collection=collection)
        _write_jsonl(args.output, tasks, asdict)
        print(f"wrote {len(tasks)} research enrichment tasks to {args.output}")
        return 0

    if args.command == "build-rights-queue":
        records = _load_many(args.inputs)
        tasks = build_rights_queue(records, collection=collection)
        _write_jsonl(args.output, tasks, asdict)
        print(f"wrote {len(tasks)} publication/rights-clearance tasks to {args.output}")
        return 0

    if args.command == "build-graph":
        from historical_engine.graph_derivation import materialize_graph

        records = _load_many(args.inputs)
        args.database.parent.mkdir(parents=True, exist_ok=True)
        with ArchiveStore(args.database) as store:
            payload = materialize_graph(records, collection, store)
            payload["database"] = str(args.database)
            payload["table_counts"] = store.stats()
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.stats_output:
            args.stats_output.parent.mkdir(parents=True, exist_ok=True)
            args.stats_output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0

    if args.command == "analyze-graph-quality":
        from historical_engine.graph_quality import write_report

        report = write_report(
            args.database,
            json_output=args.json_output,
            markdown_output=args.markdown_output,
            high_degree_threshold=args.high_degree_threshold,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "jev-config-check":
        from historical_engine.ai.typesafe_config import typesafe_config_from_env

        config = typesafe_config_from_env(dotenv_path=args.dotenv)
        print(json.dumps(config.safe_status(), indent=2, sort_keys=True))
        return 0 if config.ready_for_transport else 1

    if args.command == "build-resolution-candidates":
        from historical_engine.resolution_candidates import write_candidates

        payload = write_candidates(
            args.database,
            args.output,
            collection_id=collection.id,
            max_entity_pairs=args.max_entity_pairs,
            max_event_pairs=args.max_event_pairs,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "run-jev-decisions":
        from historical_engine.ai.batch import write_decision_batch
        from historical_engine.ai.jev import JevDecisionProvider

        provider = JevDecisionProvider.from_env(
            dotenv_path=str(args.dotenv),
            timeout_s=args.timeout,
        )
        payload = write_decision_batch(
            provider,
            args.input,
            args.output,
            collection=collection,
            agent_version=args.agent_version,
            proposal_output=args.proposal_output,
            max_requests=args.limit,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "analyze-jev-calibration":
        from historical_engine.ai.calibration import write_calibration_report

        payload = write_calibration_report(
            args.input,
            json_output=args.json_output,
            markdown_output=args.markdown_output,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "run-demo-pipeline":
        from evidence_collections.demo_history.pipeline import run_pipeline

        payload = run_pipeline(args.database)
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.stats_output:
            args.stats_output.parent.mkdir(parents=True, exist_ok=True)
            args.stats_output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0

    if args.command == "build-store":
        args.database.parent.mkdir(parents=True, exist_ok=True)
        with ArchiveStore(args.database) as store:
            observations = store.import_source_jsonl(args.records)
            temporal = store.import_claim_jsonl(args.temporal, "temporal") if args.temporal else 0
            spatial = store.import_claim_jsonl(args.spatial, "spatial") if args.spatial else 0
            entities = store.import_claim_jsonl(args.entities, "entity") if args.entities else 0
            stats = store.stats()
        payload = {
            "database": str(args.database),
            "imported_observations": observations,
            "imported_temporal_claims": temporal,
            "imported_spatial_claims": spatial,
            "imported_entity_claims": entities,
            "table_counts": stats,
        }
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.stats_output:
            args.stats_output.parent.mkdir(parents=True, exist_ok=True)
            args.stats_output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
