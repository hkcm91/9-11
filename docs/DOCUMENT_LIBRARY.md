# Public-interest document library

The first executable milestone adds a document reader and page search alongside
the 9/11 map. It reuses ArchiveStore for source observations and AI proposals;
additive `library_*` tables keep document versions, page text, processing attempts,
publication reviews, and Jev decision history. Existing maps and exports are unchanged.

## Run a local pilot

```sh
python -m pip install -e '.[dev,documents]'
archive-library ingest examples/library/pentagon-index.json
archive-library import-records src/evidence_collections/wikileaks/fixtures/real_sample.jsonl --collection wikileaks --release-id regression-metadata-sample
archive-library coverage
archive-library publication DOCUMENT_ID --public --reviewer 'Editor name' --note 'Reason this version is suitable for display'
archive-library serve
```

Open http://127.0.0.1:8879. Ingestion prints the document IDs. Repeat the publication
command for each version an editor has reviewed. Omit `--public` to withdraw a
version immediately from search, the reader, original downloads, and Jev input.
Publication approval does not verify a document's assertions. The server is a
local preview, binds only loopback, and exposes no editing or model-call endpoints.

`--database` and `--objects` are global options placed before the subcommand.
Defaults are `artifacts/library.sqlite` and `artifacts/library-objects`. Back up
both together; the search index can be recreated from versioned page records.
Pilot binaries, databases, and local credentials are not committed.

The WikiLeaks fixture is **two curated metadata records, not two full leaked
documents**. The reader labels them accordingly. The same `import-records`
command accepts normalized JSONL from existing Cablegate and War Diary adapters.
It preserves each exact input line as an object and links the upstream record ID
in metadata. The new source observation is explicitly namespaced to its release.

## Source manifest contract

A JSON array supplies `collection`, `release_id`, `source_item_id`, `source_url`,
`title`, and `format` for every item. Supported collection IDs are `september11`,
`wikileaks`, `snowden`, `pentagon_papers`, `pentagon_disclosures`, and `epstein`.
These are routing labels, not a claim that those collections are populated.

- `format`: `pdf`, UTF-8 `text` (form feed separates pages), or normalized JSON `record`.
- `path`: optional local input, resolved relative to the manifest.
- Without `path`, the operator CLI downloads `source_url` over HTTPS. Redirects
  are rejected; record the final URL explicitly. No browser fetch proxy exists.
- `sha256`: optional expected checksum, checked before ingestion.
- `document_date`, `publication_date`, `rights`, and any release-specific fields
  are preserved independently as metadata; dates are not inferred.

Version identity includes metadata, byte checksum, and extraction version.
Changed source bytes or metadata create a new, unpublished version. Identical
bytes share a content-addressed object without merging distinct source records.
Original-byte checksums are checked again for downloads and re-imports.
All pages are retained, including blank pages; these are flagged `needs_ocr`.
PDF page numbers are physical one-based PDF pages, not printed folio labels.

Ingestion processes entries independently, records failures, continues after a
bad file, and exits nonzero if any failed. Rerun the manifest to retry; successful
versions remain idempotent. Coverage counts the latest attempt per release/item,
not the number of retries. Public coverage exposes approved version counts only.
Coverage is relative to submitted manifests, not all material ever published.

## Jev integration

```sh
archive-library compare LEFT_ID RIGHT_ID --left-page 2 --right-page 7 --question same_event
```

Uses the existing TypeSafe configuration and `JevDecisionProvider.from_env()`.
Questions supported here: `same_event`, `same_entity`, `duplicate_or_derivative`.
Only approved pages with text can be sent. Each comparison makes at most one
provider call; identical requests for the same model/version use a cached result.
Each passage is capped at 12,000 characters and truncation is explicitly recorded.
Requests store immutable document IDs, page numbers, source URLs, and exact text
sent. Out-of-scope evidence IDs are rejected. The engine's `run_decision` routes
results as sensitive proposals; existing workbench review remains authoritative.
There is no automatic identity merge, claim verification, or public AI answer.

## Source expansion registry

| Collection | Discovery starting point | Next adapter work |
| --- | --- | --- |
| WikiLeaks | Existing `docs/WIKILEAKS.md`, collection adapters and release registry | Full-file manifests per publication; normalized JSONL bridge already works |
| Pentagon Papers | https://www.archives.gov/research/pentagon-papers | Enumerate each catalog volume; initial index manifest included |
| Snowden | https://github.com/joshbegley/NSA-Stories | Resolve publisher document links and record unavailable items |
| Epstein | https://www.justice.gov/epstein | Release/docket/exhibit manifests, redaction and victim-privacy review |
| 9/11 | Existing collection source registry | Export document records into the shared library |

## Deliberate limits / next milestones

This is a local, sequential pilot, not the production bulk archive. Imports are
bounded to 50 MiB/file and 2,000 PDF pages. Encrypted files are rejected. Larger
volumes need a streaming worker and explicit resource budgets. The present PDF
parser runs in the operator process; isolate it before accepting untrusted bulk
inputs. HTTPS reads have a 30-second socket timeout and no automatic retry loop.

Still to implement: complete release discovery, OCR workers and page coordinates,
attachment extraction, HTML/email formats, PostgreSQL/object-service deployment,
background queues, source change schedules, publication redaction tooling,
authenticated production review, date filters, saved sets, semantic retrieval,
and restore/load testing. No complete Snowden or Epstein corpus is bundled.
Publication restrictions currently operate on whole document versions; never
approve a version that needs passage-level redaction.

Tests cover immutable versions, re-imports, checksums, failure recovery, FTS
literal queries, page citations, publication withdrawal, HTTP original access,
blank PDF handling, Jev proposal routing/caching, and the existing engine suite.
Live Jev execution requires deployment credentials and is separate from offline tests.
