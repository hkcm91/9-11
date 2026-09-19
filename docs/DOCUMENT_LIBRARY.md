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

## Larger source batches

```sh
python -m pip install -e '.[dev,bulk-documents]'
archive-library discover-pentagon --output examples/library/pentagon-papers.json
archive-library inventory examples/library/pentagon-papers.json
archive-library bulk-ingest examples/library/pentagon-papers.json --max-total-mib 1024 --max-file-mib 600
archive-library inventory
archive-library fetch-cablegate --limit 1000 --output-dir artifacts/cablegate-validated
```

The checked-in Pentagon Papers manifest contains all 49 PDF links from the
National Archives catalog snapshot, each with a catalog identifier and source
URL. Discovery saves the original catalog HTML locally and a small provenance
receipt with its checksum. Unexpected PDF hosts, ambiguous rows, and duplicate
catalog identifiers fail discovery rather than silently producing partial data.
`--html` can reproduce discovery from a saved catalog snapshot.

`bulk-ingest` streams files to disk in 1 MiB chunks, checks their hashes, then
parses PDFs from disk. Optional PyMuPDF accelerates larger volumes; pypdf remains
the fallback. Extraction method/version is recorded, and new document identity
includes the extractor version. Existing citation IDs remain valid.

The default batch budget is 1 GiB and the per-file ceiling is 600 MiB. The
streaming limit uses at most one extra byte to detect overflow when a source
does not advertise its length. Over-budget files are deferred, not counted as
imported. Completed objects are atomic; interrupted partial downloads are not
promoted. Rerun the same command to continue. Previously indexed versions are
verified and skipped without network reads, and failed extraction can reuse a
preserved download. `--refresh` explicitly checks sources again; `--limit` caps
the number of manifest items considered. There is no byte-range partial resume
or unattended retry loop yet.

Inventory coverage distinguishes discovered, processed, failed, pending, and
published items. Publication remains a separate per-document operation. The
reader fetches one page at a time; its previous/next/jump controls and copied
citations work with full volumes. Downloads stream from the verified object
instead of loading a whole PDF into memory. Search excerpts center on matches.

The Cablegate command reuses the existing Internet Archive mirror adapter. It
requires eight complete CSV fields, a plausible formal cable reference, and a
nonempty body, skipping malformed fragments while seeking the requested count.
The source CSV, normalized JSONL, checksum, skipped-row counts, mirror URL, and
retrieval time are retained under the output directory. This is a bounded sample,
not full-release coverage; row validation does not verify the source's assertions
or certify that the mirror includes every passage of the original cable.
Imported cables remain unpublished for source review. Quarantined imports cannot
be approved for publication. Repeated identical normalized rows retain their
identity rather than creating versions from a changed retrieval timestamp.

## Source manifest fields

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

## Content integrity and reader

`archive-library audit-content` checks every published object's SHA-256, PDF page
count and contiguous page numbering. For text and source records it also compares
the stored page text with extraction from the preserved bytes. It exits nonzero
on failure. This checks local integrity, not historical accuracy or whether a
publisher/mirror omitted material. PDF pages can be viewed as original scans in
the reader, including pages awaiting OCR. Rendering requires `bulk-documents`.

Cablegate's Internet Archive CSV uses backslash-escaped quotations. The importer
now parses that dialect strictly, rejects incomplete rows and replacement
characters in bodies, preserves the whole body once, and uses `_a` publisher URLs.
The corrected release is `cablegate-ia-fulltext-v2`; earlier
`cablegate-ia-validated-sample` imports can contain truncated bodies and must be
withdrawn/quarantined, not reused. New imports remain unpublished until reviewed.
The preview labels full mirror text separately from metadata-only records.

The `warlog_html` format preserves original WikiLeaks War Diary HTML and decodes
its published `var summary` JSON string without running scripts. Publisher
redactions remain intact. This is the published narrative, not an unredacted
military original. Other HTML layouts fail extraction rather than becoming empty
documents. Original HTML is downloaded as an attachment, never embedded.

## Collection completion

**Collection coverage** shows catalog scope and per-item stages: pending,
downloaded, awaiting review, searchable, failed, quarantined, or integrity problem.
The stage is distinct from original presence, extraction, publication reviews,
OCR gaps, and the last checksum check. A failed retry retains visibility of a
previously stored version and its error. Checks verify up to 100 preserved objects
per invocation, oldest checks first; results include check times.

Only an explicitly complete catalog with an expected count matching the discovered
inventory can become complete. All items must be reviewed, searchable and verified,
with no remaining OCR pages or failed attempts. Samples and partial catalogs cannot
become complete merely because their discovered files finished processing. Completion
is relative to the recorded catalog snapshot, never all files that may exist.

```sh
archive-library completion-scopes examples/library/completion-scopes.json
archive-library inventory examples/library/snowden-published-mirror.json
archive-library inventory examples/library/epstein-doj-data-set-1.json
archive-library completion
archive-library completion --collection pentagon_papers --release-id nara-2011 --verify
archive-library bulk-ingest examples/library/snowden-published-mirror.json --limit 12 --max-total-mib 80
```

The Snowden manifest pins a third-party repository commit and records Git blob
identities and exact sizes; the importer verifies those identities before extraction.
It inventories 474 PDFs, not the complete underlying Snowden cache. The Epstein
manifest captures 50 PDF links on the first DOJ data-set-1 catalog page. Eleven
additional DOJ data sets have unenumerated scopes. Pagination and source access
remain outstanding; no missing count is invented. Catalog snapshot hashes and URLs
are in the scope registry. Parser functions in `library_catalogs` accept downloaded
tree/commit JSON or official catalog HTML, validate origins/identities, and fail on
empty or truncated inventories. Discovery does not bypass source access controls.

For ambiguous matches, select an expected item and search for a published candidate
in the dashboard. Jev assesses supplied catalog metadata and the candidate's first
6,000 characters, with a cached proposal and source citation. It does not assign
inventory items, mark files present, change counts, or grant publication approval.

## Reading briefs

Search results and the reader display a source subject heading where one can be
extracted reliably; the original identifier remains visible. Original downloads
use a sanitized readable filename plus a document-ID suffix. Stored objects and
their hashes, original metadata, and citations are unchanged.

Open **Reading brief & noteworthy passages** in the reader to create a brief.
It selects up to six text pages (opening, closing, and update/conclusion wording),
and retains exact cited excerpts including late corrections. This is an extractive
reading aid, not a generated whole-document summary. Jev evaluates whether the
proposed title is supported by the excerpts; an uncertain or negative assessment
keeps the original title in the brief. A supported suggestion is still unverified.
Noteworthy passages use local wording markers, not model newsworthiness scoring.

Briefs are cached and exportable as readable Markdown with page citations, source
URL, original identifier, checksum and coverage limitations. Creating a new brief
makes one Jev call; identical requests reuse the result. Withdrawn documents cannot
be retrieved or exported. No bulk model processing occurs automatically.

## Question-led investigations

**Jev investigator** accepts a question, name, event, or specific claim. Choose
relevance, supporting evidence, or conflicting evidence; optionally restrict the
collection. Quick/deeper passes assess at most 3/6 pages. Retrieval removes common
question words, searches up to 12 terms with FTS OR, reranks up to 80 candidates
by term coverage, groups identical text, and selects at most two pages per document.
This is bounded keyword retrieval, not exhaustive semantic or internet search.

Jev sees an exact window around matching text (up to 8,000 characters), plus the
last 2,000 characters when the page extends beyond that window, to retain late
updates. Omitted middle text is disclosed. Results include the exact supplied
passages, source-page links, model judgments, unknowns, caveats and verification
steps. Runs are saved locally and can be reopened or exported as a JSON evidence
sheet. Cached assessments avoid repeated calls; provider failure stops the run
while preserving earlier results. Withdrawal hides saved findings and export
rechecks source publication. The historical run counts describe the original run.
No automatic factual answer, publication, autonomous background run or external
source discovery is implied. Empty results describe this search, not reality.

## Changing-account leads

The reader's **Lead inbox** pilots one beat: initial accounts followed by updates
or corrections on the same page. **Find leads in archived text** scans public text
locally and adds at most 25 new candidates. **Find and assess up to 3 leads with
Jev** scans, then assesses up to three unassessed inbox candidates. It stops at a
provider failure and retains completed results. There is no recurring background
job, automatic publishing, or whole-corpus model upload.

Candidates contain exact source offsets and excerpts for both the initial account
and later update, full-page links, limitations, and concrete verification steps.
Whitespace-normalized identical page text is deduplicated; this does not establish
independent corroboration. Jev assesses the narrow claim that the later passage
materially revises the same incident's initial assessment. Its result remains a
proposal, including `unknown` and negative answers. Confidence is not a
newsworthiness score. Latest discoveries appear first.

Reviewers can move leads to investigating, dismiss them, or return them to the
inbox with an explanatory note. Review history is retained. Withdrawn documents
hide their leads and cannot be assessed, even when results were cached. Scope is
deliberately limited to wording-based candidates on individual pages; cross-document
chronologies, semantic candidate retrieval, independent corroboration and other
reporting beats are not implemented. Scanned pages without OCR cannot be searched.

## Page comparisons

The local reader includes a **Compare pages with Jev** panel. Open a page, select
it as the first comparison page, then select another page as the second. Choose
same event, same entity, or duplicate/derivative and click **Compare with Jev**.
The explicit request sends the selected passages to TypeSafe; it does not send
the archive corpus. The result shows model confidence, review status, citations,
and the exact passages supplied, including any truncation.

Copy `.env.example` to the ignored `.env` file and set `TYPESAFE_API_KEY` locally.
Use **Check connection settings** after saving. Local file settings are read fresh;
process environment overrides them. Configuration status is not a live connection
test: the first comparison validates the actual deployment. The browser never
receives the key. Missing credentials disable comparisons; provider failures are
reported without exposing upstream response details. The loopback POST endpoint
requires same-origin JSON and serializes comparisons to avoid duplicate in-flight
requests. This is not an authenticated multi-user deployment.

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
| Pentagon Papers | https://www.archives.gov/research/pentagon-papers | Complete 49-PDF catalog manifest and bulk import available |
| Snowden | https://github.com/joshbegley/NSA-Stories | Resolve publisher document links and record unavailable items |
| Epstein | https://www.justice.gov/epstein | Release/docket/exhibit manifests, redaction and victim-privacy review |
| 9/11 | Existing collection source registry | Export document records into the shared library |

## Deliberate limits / next milestones

This is a local, sequential archive, not the production service. The original
`ingest` command remains bounded to 50 MiB/file; `bulk-ingest` supports larger
PDFs within explicit byte budgets. Both cap PDF extraction at 2,000 pages per
file and reject encrypted files. The PDF parser runs in the operator process;
isolate it before accepting untrusted bulk inputs. Bulk HTTPS reads have a
60-second socket timeout. Restore/load testing is still required for deployment.

Still to implement: release discovery beyond the Pentagon Papers, OCR workers and page coordinates,
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
