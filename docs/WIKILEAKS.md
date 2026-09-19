# WikiLeaks collection

The WikiLeaks collection is the first non-9/11 production-style corpus running
on the Historical Evidence Engine.

It currently supports:

- PlusD / Cablegate diplomatic records
- Iraq / Afghanistan War Diaries SIGACT records
- CSV, JSON, JSONL and NDJSON local imports
- collection-aware research roles and work-queue semantics
- provenance-preserving import into the existing SQLite evidence store

## Commands

```bash
archive-ingest import-wikileaks-plusd cables.csv --limit 100 --output artifacts/raw/plusd.jsonl
archive-ingest import-wikileaks-war-diaries war-diaries.csv --limit 100 --output artifacts/raw/war-diaries.jsonl

archive-ingest --collection wikileaks profile-jsonl artifacts/raw/*.jsonl --output artifacts/reports/profile.json
archive-ingest --collection wikileaks derive-temporal-claims artifacts/raw/*.jsonl --output artifacts/reports/temporal-claims.jsonl
archive-ingest --collection wikileaks derive-spatial-claims artifacts/raw/*.jsonl --output artifacts/reports/spatial-claims.jsonl
archive-ingest --collection wikileaks derive-entity-claims artifacts/raw/*.jsonl --output artifacts/reports/entity-claims.jsonl
archive-ingest --collection wikileaks build-work-queue artifacts/raw/*.jsonl --output artifacts/reports/work-queue.jsonl
```

## Evidence semantics

A leaked record is a source record, not an established fact.

The collection ontology explicitly preserves the distinction between mention,
association, allegation, corroboration, contradiction and established claims.
Named-person entity resolution and consequential relationship/claim linking are
routed for human review.

## War Diaries

MGRS and region fields are preserved in raw metadata. They do not automatically
become a precise `location_raw` value. If no explicit named location exists,
the record remains unresolved spatially and the work queue creates an
`event_location` research task.

Casualty fields are likewise preserved as source assertions and are not
promoted into verified claims merely because they are present in a record.

## Cablegate

Formal references/MRNs, classification, routing destinations, TAGS and
cross-cable references are retained in `metadata_raw`. Cable-to-cable
references are candidates for future typed graph relationships; ingestion does
not automatically treat a reference as corroboration.

## Architecture

This collection lives under `src/evidence_collections/wikileaks/` rather than
inside the generic engine. The engine remains unaware of WikiLeaks-specific
source IDs and event semantics.


## First-pass evidence graph

The collection now supplies the engine's generic `derive_graph` hook.

For Cablegate records it deterministically proposes:

- one document node for the cable
- sender/origin organization nodes
- destination organization nodes
- referenced-cable document nodes
- typed `sent_from`, `sent_to`, and `references_document` relationships

For War Diaries records it proposes:

- one document node representing the source record
- one `sigact` event
- the reporting military unit when available
- region and raw MGRS place nodes
- typed `describes`, `reported_by`, `located_in`, and `occurred_at` relationships

Every derived object remains `proposed`, cites the source record, and carries a
deterministic provenance method. The graph pass does not assert corroboration or
established fact.

Build the graph with:

```bash
archive-ingest --collection wikileaks build-graph artifacts/raw/*.jsonl \
  --database artifacts/wikileaks.sqlite \
  --stats-output artifacts/reports/graph-stats.json
```

## Real regression sample

`src/evidence_collections/wikileaks/fixtures/real_sample.jsonl` contains two
small records manually transcribed from the public archive for regression
testing:

- PlusD cable `09STATE122615_a`
- War Diaries record `7893F7C5-E13B-4C3D-8B4A-75B93202ED14`

The fixture intentionally contains only enough source metadata to exercise
provenance, routing, event and relationship behavior; it is not intended to
replace the original documents.

Running the `wikileaks-sample` GitHub Action without dataset URLs uses this
fixture automatically. Supplying public CSV URLs instead exercises up to the
requested sample limit (100 by default).


## 200-record validation milestone

The `wikileaks-sample` workflow now doubles as a graph-quality validation job.

Set:

- `plusd_url` to a public Cablegate/PlusD CSV
- `war_diaries_url` to a public War Diaries CSV
- `sample_limit` to `100`

When both datasets are supplied, the workflow requires at least 100 normalized
records from each source, producing the intended 200-record validation corpus.

After graph materialization it runs:

```bash
archive-ingest --collection wikileaks analyze-graph-quality \
  --database artifacts/wikileaks.sqlite \
  --json-output artifacts/reports/graph-quality.json \
  --markdown-output artifacts/reports/graph-quality.md
```

The quality report checks:

- source counts
- node / event / relationship counts
- relationship predicates and assertion levels
- placeholder entities such as `Not Provided`
- duplicate canonical-name/type pressure
- isolated nodes
- dangling relationship endpoints
- events with missing or invalid times
- graph relationship density
- high-degree nodes that may indicate over-broad normalization

The report is descriptive. It never merges entities, removes records, upgrades
assertion strength, or verifies a claim automatically.

For bulk-source discovery, prefer stable public mirrors or institutional archive
copies rather than scraping the live search UI repeatedly. The workflow keeps
dataset URLs as explicit inputs so the exact source used for a validation run is
preserved in the Actions run metadata.


## Entity and event resolution candidate queue

After graph materialization, the engine can now generate narrow review questions
for ambiguous graph pairs:

```bash
archive-ingest --collection wikileaks build-resolution-candidates \
  --database artifacts/wikileaks.sqlite \
  --output artifacts/reports/resolution-candidates.jsonl
```

The queue currently emits the engine's existing closed decision types:

- `same_entity`
- `same_event`

Each row contains:

- subject node id
- object node id
- collection id
- evidence source-record ids
- heuristic candidate score
- structured context explaining why the pair was surfaced

The deterministic candidate stage does **not** answer the question. It only
reduces the search space so a human or a narrow decision provider such as Jev
does not need to compare every possible pair.

### Entity candidates

Potential same-entity pairs are surfaced from normalized name similarity within
the same entity type. Punctuation/format variants such as `U.S. Embassy Cairo`
versus `US Embassy Cairo` can become candidates, while unrelated names are
left alone.

No canonical entity is merged or rewritten.

### Event candidates

Potential same-event pairs require compatible event type and a bounded time
window, then combine title similarity with structured metadata such as event
category and source event type.

The result is a question such as:

```json
{
  "question": "same_event",
  "subject_id": "event:...",
  "object_id": "event:...",
  "evidence_ids": ["wikileaks-war-diaries:...", "wikileaks-war-diaries:..."],
  "context": {
    "candidate_score": 0.81,
    "time_delta_hours": 0.5,
    "shared_category": true,
    "shared_type": true
  }
}
```

A positive model answer still enters the proposal/review lifecycle. It does not
merge events automatically.

### Jev handoff

The output schema is intentionally the same `DecisionRequest` vocabulary used
by `historical_engine.ai`. The existing Jev provider slot can therefore
consume this queue once a real Jev transport/API client is configured.

This keeps responsibilities separate:

```text
graph
  -> deterministic candidate generation
  -> Jev / other DecisionProvider
  -> confidence routing
  -> proposed entity_resolution / event_link
  -> human review
  -> accepted or rejected relationship
```


## Batch decision runner

The engine now includes a provider-agnostic batch runner for decision queues.

Programmatically:

```python
from historical_engine.ai import write_decision_batch

summary = write_decision_batch(
    provider,
    "artifacts/reports/resolution-candidates.jsonl",
    "artifacts/reports/resolution-decisions.jsonl",
    collection=wikileaks_collection,
    agent_version="...",
    proposal_output="artifacts/reports/resolution-proposals.jsonl",
)
```

The runner:

- loads `DecisionRequest` JSONL
- rejects cross-collection requests
- asks the configured `DecisionProvider`
- validates the provider's answer against the question's closed answer space
- applies collection-specific confidence routing
- writes full decision traces
- writes only validated `proposed` proposal envelopes for rows that survive routing

It cannot create a reviewed/verified graph edge.

The existing `JevDecisionProvider` is the intended first real provider for this
queue. A concrete Jev transport is deliberately not hard-coded until TypeSafe's
early-access API documentation supplies a stable endpoint/request contract.


## TypeSafe / Jev credentials

Local development uses environment variables. The repository includes
`.env.example`, while real `.env` files are ignored by Git.

Create your local file:

```bash
cp .env.example .env
```

Then fill in:

```dotenv
TYPESAFE_API_KEY=your_real_key_here

# These are the documented defaults and can usually be omitted:
TYPESAFE_API_URL=https://api.typesafe.ai/v1/systemone
TYPESAFE_MODEL=jev-latest
TYPESAFE_API_AUTH_HEADER=Authorization
TYPESAFE_API_AUTH_PREFIX=Bearer
```

Do not commit the real `.env` file.

Check configuration without exposing the secret:

```bash
archive-ingest jev-config-check
```

Example safe output:

```json
{
  "api_key_configured": true,
  "api_url_configured": true,
  "auth_header_configured": true,
  "auth_prefix_configured": true,
  "model": "jev-latest",
  "ready_for_transport": true
}
```

The command never prints the API key or endpoint credentials.

### GitHub Actions

In the repository settings create:

**Secret**

- `TYPESAFE_API_KEY`

**Optional Actions variables**

- `TYPESAFE_API_URL` (defaults to `https://api.typesafe.ai/v1/systemone`)
- `TYPESAFE_MODEL` (defaults to `jev-latest`)
- `TYPESAFE_API_AUTH_HEADER` (defaults to `Authorization`)
- `TYPESAFE_API_AUTH_PREFIX` (defaults to `Bearer`)

The `wikileaks-sample` workflow injects those values into the process
environment and runs a secret-safe configuration check.

### Real Jev transport

The documented TypeSafe System One API is now wired through
`TypeSafeHttpTransport`.

It sends a POST request to `/v1/systemone` with:

- the candidate's structured state
- model `jev-latest`
- one Choice question named `decision`
- the engine's exact closed answer vocabulary as the Choice criteria

The response's `choice`, `probabilities`, and `confidence` are translated
back into the engine's validated `DecisionResponse` and then pass through the
existing proposal/confidence-routing pipeline.

Run a queue locally with:

```bash
archive-ingest --collection wikileaks run-jev-decisions \
  artifacts/reports/resolution-candidates.jsonl \
  --output artifacts/reports/resolution-decisions.jsonl \
  --proposal-output artifacts/reports/resolution-proposals.jsonl
```

The GitHub `wikileaks-sample` workflow also has a `run_jev` checkbox. It is
off by default so normal archive validation does not spend TypeSafe API credits.


## 25-candidate live Jev calibration

Before scaling Jev to the full candidate queue, the WikiLeaks sample workflow
now supports a capped live calibration run.

Use workflow inputs:

- `run_jev = true`
- `jev_candidate_limit = 25` (default)
- supply real PlusD / War Diaries dataset URLs when testing real records

The live runner enforces the cap before making API calls:

```bash
archive-ingest --collection wikileaks run-jev-decisions \
  artifacts/reports/resolution-candidates.jsonl \
  --output artifacts/reports/resolution-decisions.jsonl \
  --proposal-output artifacts/reports/resolution-proposals.jsonl \
  --limit 25
```

After the live calls it automatically builds:

- `artifacts/reports/jev-calibration.json`
- `artifacts/reports/jev-calibration.md`

The calibration report summarizes:

- number of real Jev decisions
- same-entity vs same-event question counts
- answer distribution
- mean/min/max confidence
- confidence bands
- routing outcomes
- proposal vs no-proposal counts
- medium-confidence / human-review cases prioritized for manual inspection

The decision JSONL also preserves Jev's returned probability distribution and
usage metadata where available.

This stage is deliberately small. Its purpose is to evaluate whether Jev's
confidence is useful on the archive's actual candidate distribution before
raising the API-call limit.
