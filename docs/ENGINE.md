# The Historical Evidence Engine

A reusable, provenance-first engine for historical archives. The September 11
collection is the first corpus running on it; the engine itself knows nothing
about September 11.

```text
Historical Evidence Engine
        |
        +-- september11     the working 9/11 archive and research pipeline
        +-- demo_history    a tiny synthetic corpus, architectural validation
        +-- future collections
```

## The rule everything else serves

> **Never replace the source record with an AI guess.**

Raw observations are immutable. Everything derived — a time, a place, a name, a
link between two records — is stored *separately*, as a claim, proposal,
relationship or reviewed assertion, and carries:

* provenance (method, agent identity, agent version)
* evidence (at least one cited source record)
* confidence
* review status
* revision history where the assessment can change

AI output never silently becomes verified history. There is exactly one path
from a model's answer to the database — `historical_engine.ai.run_decision` —
and its only possible outputs are a proposal with status `proposed`, or
nothing.

## What the engine does

| Area | Module |
| --- | --- |
| Source registry (YAML, composable) | `historical_engine.sources` |
| Record-role classification | `historical_engine.roles` |
| Collection abstraction | `historical_engine.collection` |
| Collection discovery | `historical_engine.collection_registry` |
| Ontologies and sensitive policy | `historical_engine.ontology` |
| Enrichment prioritisation | `historical_engine.quality` |
| Research work queues | `historical_engine.work_queue`, `.work_rules` |
| Claims serialization | `historical_engine.claims` |
| Evidence graph model | `historical_engine.models` |
| Proposal validation | `historical_engine.proposals` |
| Confidence routing | `historical_engine.routing` |
| AI provider interfaces | `historical_engine.ai` |
| SQLite graph schema | `historical_engine.storage` |

Ingestion, normalization, duplicate detection, the SQLite evidence store, the
query facade and the reviewer workbench live in `archive.*` and are shared by
every collection; see `docs/ENGINE_REFACTOR.md` for why that package kept its
name.

## What a collection defines

A collection is one historical corpus. It supplies:

* **id, name, description**
* **source registry** — `sources.yaml`
* **ontology** — `ontology.yaml`: entity types, event types, relationship
  predicates, record roles, assertion levels, sensitive-content policy
* **record-role classification** — an ordered list of named rules
* **interpretation rules** — what a particular source's metadata *means*
* **task applicability and priority multipliers**
* **routing thresholds** per task type
* **hooks** — deterministic derivations and other opt-in extension points

Everything except the hooks can be pure YAML. `BaseCollection` supplies generic
behaviour for all of it, so the minimum viable collection is two YAML files and
one line of Python.

## The claim and proposal lifecycle

```text
raw source
  -> normalized observation        (immutable, every ingestion preserved)
  -> candidate claim               (deterministic derivation, or a research task)
  -> proposal                      (agent identity + evidence + confidence)
  -> review                        (a named human, recorded separately)
  -> reviewed / verified / disputed / rejected
```

Rules the store enforces:

* an agent may only submit `review_status="proposed"`;
* a proposal cannot be verified without first being reviewed;
* `rejected` and `verified` are terminal;
* every review is appended to `proposal_reviews` with the previous status, the
  new status and the reviewer — corrections supersede, they do not erase.

## Claims are not facts, and edges are not all the same

The model keeps these apart deliberately:

| Stage | Where it lives |
| --- | --- |
| raw source observation | `source_observations` |
| extracted mention | entity/temporal/spatial claim, status `proposed` |
| proposed claim | `agent_proposals` |
| reviewed / verified / disputed claim | claim `status` + `proposal_reviews` |
| relationship hypothesis | `relationships` with a low assertion level |
| established relationship | `relationships`, `established`, human-set only |

A relationship carries an **assertion level**, and the engine refuses to let
you leave it unsaid:

```text
mentioned  associated  alleged  witnessed
reported   corroborated  contradicted  established
```

`corroborated` and `established` can only be set by a human actor. A generic
"connected to" edge would erase exactly the distinction that matters most in a
sensitive collection, so there isn't one.

## Claim-to-claim reasoning

Claims relate to each other explicitly, with their own provenance and evidence:

```text
Claim B supports Claim A
Claim C contradicts Claim A
Claim D partially_corroborates Claim A
Claim E supersedes Claim A
```

When two sources disagree, both claims stay and the disagreement is recorded as
a `contradicts` edge. Nothing is averaged, scored or flattened into a single
truth. The `demo_history` collection ships a worked example.

## The evidence graph

```text
        source record ──observed as──> source observation
              │
              ├──evidence for──> temporal / spatial / entity claim
              │                          │
              │                    claim_relations (supports, contradicts, …)
              │
              └──subject of──> relationship ──> entity
                                    │             │
                                    │           entity_aliases
                                    └──────────> event
```

Every claim, relationship and entity points back at the source records that
justify it. Nothing in the graph replaces a source record; the graph is a layer
of interpretation sitting on top of an archive that stays intact underneath it.

## AI boundaries

AI helps organise and infer. It does not write history.

* **Providers are protocols**, injected, never imported from a vendor SDK:
  `DecisionProvider`, `GenerativeProvider`, `EmbeddingProvider`,
  `VisionProvider`, `TranscriptionProvider`. Deterministic fakes ship with the
  engine, so tests need no credentials.
* **Questions are closed.** A decision provider is asked "same event?", "same
  entity?", "supports claim?", "contradicts claim?", "relevant to thread?",
  "firsthand or secondhand?", "duplicate or derivative?", "route to human
  review?" — each with a declared answer space. An answer outside it is
  rejected before anything is recorded.
* **Jev has a slot, not an integration.** `historical_engine.ai.jev` defines
  the plug point and the guarantees; no proprietary endpoint or auth scheme is
  invented. Supply a `JevTransport` to wire a real deployment.
* **Routing** turns confidence into one of: accept as proposal, escalate,
  human review, weak candidate, discard. Thresholds are per collection and per
  task type — never global constants.
* **Out of scope, permanently**: facial recognition, identifying people from
  images, guilt or suspicion scoring, and collapsing conflicting accounts into
  a single truth score.

## Adding a new collection

1. **Create the package.** `src/evidence_collections/<id>/` with an
   `__init__.py` exporting `build_collection`.
2. **Define the ontology.** `ontology.yaml`. Use `extra_entity_types`,
   `extra_event_types`, `extra_predicates` to *add* to the engine's generic
   vocabulary rather than replacing it. Declare the sensitive policy honestly.
3. **Register the sources.** `sources.yaml`, one entry per custodial source,
   with rights status and rights notes filled in — public visibility is not
   permission to redistribute.
4. **Select or implement adapters.** Reuse the generic Internet Archive, Omeka
   or ArcGIS feature-service readers where the mechanism fits; write a new one
   only when the source's shape genuinely differs.
5. **Define rules and hooks.** Subclass `BaseCollection`; override
   `role_rules()` if the corpus needs its own classification, and supply
   `CollectionHooks` for deterministic derivations. Override nothing else
   unless you have a reason.
6. **Register it.** Add the id to `BUILTIN_COLLECTIONS` in
   `src/evidence_collections/__init__.py`.
7. **Run ingest**, then `archive-ingest --collection <id> build-work-queue …`
   and review what the queue asks for. If it asks the wrong questions, the
   ontology or the role rules are wrong — not the engine.

A collection must not import another collection; `tests/test_engine_purity.py`
enforces that, along with the rule that the engine imports neither.

## CLI

```bash
archive-ingest list-collections --verbose
archive-ingest --collection september11 list-sources
archive-ingest --collection september11 build-work-queue records.jsonl --output queue.jsonl
archive-ingest run-demo-pipeline --database demo.sqlite
archive-query --database archive.sqlite nearby --lat 40.71 --lon -74.01
```

`--collection` is optional. When it is omitted the transitional default
`september11` applies, so every pre-existing command keeps working unchanged.
Set `HISTORICAL_ENGINE_COLLECTION` to change that default without editing call
sites. The default lives in `src/archive/collections_compat.py`, is marked
transitional there, and is the only place outside
`src/evidence_collections/` where a collection is named.
