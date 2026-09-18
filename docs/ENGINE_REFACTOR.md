# Engine Refactor — Architecture Audit and Migration Notes

This document records the audit that preceded the extraction of a reusable
**Historical Evidence Engine** from the September 11 archive pipeline, and the
migration decisions that followed.

Target shape:

```text
Historical Evidence Engine
        |
        +-- september11 collection   (the existing, working pipeline)
        +-- demo_history collection  (tiny synthetic architectural validation)
        +-- future collections
```

The engine is an evidence-preserving historical knowledge system. The
fundamental rule is unchanged by this refactor:

> Never replace the source record with an AI guess. Raw observations remain
> immutable. Derived information stays separately represented as claims,
> proposals, relationships and reviewed assertions carrying provenance,
> evidence, confidence, method, agent identity, review status and revision
> history.

## Baseline

`pytest -q` on the pre-refactor tree: **110 passed**. Every phase of this
refactor keeps that suite green; new tests are added on top.

## Package layout

| Path | Contents |
| --- | --- |
| `src/historical_engine/` | Generic engine. Contains no collection-specific assumptions. |
| `src/evidence_collections/<id>/` | One directory per collection: ontology, sources, rules, hooks, adapters. |
| `src/archive/` | The original package. Kept as the stable public API / compatibility layer, now delegating generic work to the engine and 9/11 behaviour to the `september11` collection. |

### Why `evidence_collections/` and not `collections/`

The requested layout named the directory `collections/`. `src/` is on
`pythonpath`, so a top-level package named `collections` would shadow the
Python standard library's `collections` module for the whole process and break
`dataclasses`, `typing` and most of the runtime. The directory is therefore
named `evidence_collections/`. The conceptual separation the layout asked for
is preserved exactly; only the directory name differs.

### Why `src/archive/` still exists

`archive` is the installed package behind the `archive-ingest`,
`archive-query` and `archive-photo-map-info` console scripts and behind every
existing test and CI workflow. Mass-renaming it would have produced a large,
risky diff with no architectural gain. Instead each `archive` module either
(a) still owns genuinely generic code that has no better home, or (b) became a
thin re-export of the engine / the `september11` collection. Import paths that
worked before the refactor still work.

## Phase 1 audit — component classification

Categories: **G** generic engine infrastructure · **A** reusable adapter
infrastructure · **C** 9/11 collection configuration · **B** 9/11-specific
business logic · **P** presentation/explorer concern · **T** temporary Phase-0
code.

| Current file | Class | Current responsibility | Target responsibility | Moves? | API compat required | Migration risk |
| --- | --- | --- | --- | --- | --- | --- |
| `src/archive/models.py` | G | `SourceItem`, claim dataclasses, `ReviewStatus`, `EntityKind`, `EntityRole` | Stays the canonical record/claim vocabulary; engine consumes it structurally via the `SourceRecord` protocol so the engine never imports `archive` | No | Yes — imported by every adapter and test | Low. `EntityKind.RESPONDER_UNIT` is responder-specific; the *engine's* generic entity vocabulary (`historical_engine.models.graph.EntityType`) uses `unit`, and the 9/11 ontology extends it with `responder_unit`. |
| `src/archive/registry.py` | G | Load `sources.*.yaml` into `SourceRegistryEntry` | Generic source registry moves to `historical_engine.sources`; `archive.registry` re-exports | Yes | Yes — `load_source_registry`, `enabled_sources`, `SourceRegistryEntry` | Low. Loader gained a generic `sources_from:` composition key. |
| `config/sources.phase0.yaml` | C | The 9/11 source registry | Content moves to `evidence_collections/september11/sources.yaml`; the old path becomes a `sources_from:` shim | Yes | Yes — referenced by CLI default, tests and workflows | Low, covered by tests asserting the old path still loads. |
| `src/archive/work_queue.py` | G + B | Task construction *and* hardcoded source-ID → role mapping | Generic queue engine moves to `historical_engine.work_queue`; role/applicability/priority/instruction decisions are asked of the active `Collection` | Yes | Yes — `tasks_for_item`, `build_work_queue`, `build_rights_queue`, `EnrichmentTask` | **Highest risk in the refactor.** Role classification was an ordered `if` chain interleaving generic and 9/11 rules; splitting it naively changes results. Mitigated by modelling classification as an explicit *ordered rule list* the collection composes (see below). |
| `src/archive/quality.py` | G + C | Field weights (generic) + `SOURCE_VALUE` per 9/11 source (collection config) | Weights and scoring move to `historical_engine.quality`; per-source value is asked of the collection | Yes | Yes — `prioritize_item`, `prioritize_records`, `EnrichmentPriority`, `WEIGHTS` | Low. `archive.quality.SOURCE_VALUE` kept as a deprecated re-export of the 9/11 collection's table. |
| `src/archive/heuristics.py` | B | FDNY "Incident Action Plan: m/d/y" title parsing | Moves conceptually into the 9/11 collection's rules; module kept as a re-export | No (re-exported) | Yes | Low. |
| `src/archive/derived.py` | B | Deterministic claims keyed on `source_id` (`internet-archive-…`, `archdisk-…`, `nist-…`, 911DA collection 267) | Derivations become 9/11 collection rules registered through a generic derivation hook | Logic moves, module keeps API | Yes — `derive_*_claims`, `serialize_*_claim` | Medium. Output must stay byte-identical; covered by existing tests. |
| `src/archive/voices.py` | B | Voices of 9.11 filename parsing | 9/11 collection rule; module kept as re-export | No | Yes | Low. |
| `src/archive/dedupe.py` | G | Cross-source duplicate candidates | Generic. Stays. | No | Yes | Low. |
| `src/archive/profiling.py` | G | Metadata coverage profile | Generic. Stays. | No | Yes | Low. |
| `src/archive/corpus.py` | G | JSONL load + snapshot reconciliation | Generic. Stays. | No | Yes | Low. |
| `src/archive/proposals.py` | G | Proposal validation + agent-cannot-self-verify guarantee | Moves to `historical_engine.proposals`; `archive.proposals` re-exports. Proposal-type vocabulary extended. | Yes | Yes | Low. Only additive changes to the allowed-type set; no relaxation of evidence/identity rules. |
| `src/archive/store.py` | G | SQLite evidence store, review lifecycle | Stays; schema extended **additively** with collection/entity/event/relationship/claim-relation/revision tables | No | Yes | Medium — schema version bump, additive `CREATE TABLE IF NOT EXISTS` only, no destructive migration. |
| `src/archive/query.py`, `query_cli.py` | G + P | Read-only query facade | Generic. Stays. | No | Yes | Low. |
| `src/archive/workbench.py` | P | Reviewer surface payloads | Presentation. Stays. | No | Yes | Low. |
| `src/archive/pipeline.py` | G | `SourceAdapter` / `EnrichmentAgent` protocols | Generic protocol home. Stays. | No | Yes | Low. |
| `src/archive/cli.py` | G + C | Subcommands, hardcoded registry default | Gains `--collection`; registry default resolved through the collection | No | Yes | Low. |
| `src/archive/adapters/internet_archive.py` | A + C | Internet Archive search/metadata + the `internet-archive-understanding-911` source id | Mechanism is a generic Internet Archive collection adapter; the source id/name/collection are configuration | Parameterised in place | Yes | Low — defaults unchanged. |
| `src/archive/adapters/september11digital.py` | A + C | Omeka API client bound to 911digitalarchive.org | Generic Omeka adapter with a configured base URL / source id | Parameterised in place | Yes | Low. |
| `src/archive/adapters/arcgis_photo_map.py` | A + C | ArcGIS instant-app + feature-service reader | Generic ArcGIS feature-service mechanism, 9/11 app id as config | Parameterised in place | Yes | Medium — the app-id resolution logic is intricate; left intact. |
| `src/archive/adapters/nist_wtc.py` | B | NIST repository entry-point inventory | 9/11-specific; stays, re-exported through the collection's adapter namespace | No | Yes | Low. |
| `src/archive/adapters/nist_organized.py` | B | NIST Drive hierarchy + NIST claim derivation | 9/11-specific; stays, re-exported through the collection | No | Yes | Low — largest module, deliberately untouched. |
| `src/archive/photo_map_inventory.py` | T + C | `archive-photo-map-info` console script | Transitional Phase-0 tool; unchanged | No | Yes | Low. |
| `.github/workflows/*.yml` | T/C | Phase-0 sampling and inventory jobs | Unchanged paths keep working via the registry shim | No | Yes | Low. |

### Known pre-existing inconsistency (not "fixed" by this refactor)

The source registry declares the September 11 Digital Archive as
`september11-digital-archive`, while `work_queue.py`, `derived.py` and
`quality.py` key on `september-11-digital-archive` (extra hyphen). Both
spellings are live in tests. Silently unifying them would change work-queue and
priority output for real corpora, so the 9/11 collection recognises **both**
spellings and the divergence is recorded here rather than papered over.

## The ordered-rule technique (work-queue role classification)

The original `_record_role` was a single ordered `if` chain that interleaved
collection-specific and generic tests:

```text
1 source_id == internet-archive-understanding-911   -> broadcast   (9/11)
2 source_id == archdisk-911-photo-map               -> photo       (9/11)
3 source_id == september-11-digital-archive + coll  -> doc/testimony/audio (9/11)
4 source_id == nist-wtc-disaster-repository         -> repository  (9/11)
4'  OR media == "repository_entry"                  -> repository  (generic)
5 "incident action plan" in title                   -> document    (9/11)
5'  OR media in {document,text,pdf}                 -> document    (generic)
6 "voices of 9.11"/"oral history" in collection     -> testimony   (9/11 / generic)
7 "sonic memorial" in collection                    -> audio       (9/11)
7'  OR media in {audio,sound}                       -> audio       (generic)
8 media in {photo,image}                            -> photo       (generic)
9 media in {video,movie,film}                       -> video       (generic)
```

Hoisting all 9/11 tests above all generic tests would change the answer for,
say, a PDF inside a "Voices of 9.11" collection. So classification is modelled
as an explicit **ordered list of named rules**. The engine publishes the generic
rules; a collection returns the ordered list it wants, freely interleaving its
own. `September11Collection.role_rules()` reproduces the original order
one-for-one, which is why existing work-queue output is unchanged.

## What remains 9/11-specific after the refactor

Deliberately, and by design:

* `evidence_collections/september11/` — ontology, source registry, role rules,
  derivation rules, hooks, adapter namespace.
* `src/archive/adapters/nist_wtc.py`, `nist_organized.py` — NIST-shaped
  scrapers with no generic equivalent worth extracting today.
* `src/archive/heuristics.py`, `voices.py`, `derived.py` — kept as stable
  import paths; the behaviour is registered with the 9/11 collection.
* `src/archive/photo_map_inventory.py` — Phase-0 operator tool.

Everything under `src/historical_engine/` is free of collection-specific
identifiers; `tests/test_engine_purity.py` enforces that automatically and the
sole allowed exception (a transitional default in the CLI, not in the engine)
is documented in `docs/ENGINE.md`.

## Migration order actually followed

1. Audit (this document).
2. Engine skeleton: records protocol, roles, ontology, collection abstraction,
   collection registry, generic source registry.
3. September 11 collection wrapping existing behaviour; source registry moved
   with a compatibility shim at the old path.
4. Collection-aware work queue and prioritisation.
5. Generic graph model (collection/entity/alias/event/relationship/evidence/
   revision) plus additive SQLite migration.
6. Claim-to-claim relationships and assertion levels.
7. AI provider interfaces, Jev decision-provider slot, confidence routing.
8. `demo_history` collection.
9. CLI `--collection`, documentation, tests.

The repository is runnable and the full test suite green after every step.
