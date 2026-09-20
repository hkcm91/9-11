# WikiLeaks coverage and full imports

The publisher release index currently yields 65 release entries. Register
`examples/library/wikileaks-release-scopes.json` with `completion-scopes` to
show them in the completion desk. This index is a discovery snapshot, not a
complete list of every historical publication. Shared portals are kept as
separate named releases. No release is counted as acquired merely because its
landing page is listed.

## Full Cablegate transport

Run `python -m archive.library_cli fetch-cablegate-full` to preserve the entire
Internet Archive `wikileaks-cables-csv/cables.csv` transport and import all rows.
There is no sample limit by default. `--max-records N` deliberately pauses the
import after N additional rows. Running the same command resumes the download
or import. The default directory is `artifacts/wikileaks-bulk`.

The catalog advertises 1,730,507,223 bytes and SHA-1
`9a3c594cf96acdbef98fde58d0556520f3e73c92`. Metadata is pinned locally before
downloading. The downloader checks exact size and source checksum and records
a local SHA-256; the importer checks SHA-256 again before parsing. Interrupted
downloads use exact HTTP byte ranges; a server ignoring ranges cannot corrupt
the retained partial file. Both stages retain a 10 GiB free-space reserve.

Full cable bodies use the source's headerless, backslash-escaped CSV dialect.
Multiline records have exact byte offsets into the preserved transport. SQLite
stores a checkpoint after each processed row. Malformed references, missing
fields and damaged Unicode are counted in `library_bulk_rejections`, with
offsets allowing inspection of the original bytes. CSV syntax errors stop
the job at its last good record instead of discarding the remainder.

Existing identical bodies are reused, preserving publication decisions.
New records retain the existing publication-review gate. The completion desk
shows their acquired/extracted status without claiming they are published.
No Jev requests or paid inference calls occur during bulk ingestion.

`library_bulk_jobs.state_json` reports rows, imported records, reused bodies,
rejections, byte offset and end-of-file status. `complete` here means the CSV
was consumed; it does **not** certify all rows accepted, all publisher pages
matched, all attachments acquired, or all WikiLeaks releases archived.

## Afghan War Diary transport

`python -m archive.library_cli fetch-afghan-full` preserves and verifies the
16,076,742-byte `WikileaksWarDiaryCsv/afg-war-diary.csv.7z` mirror. Its advertised
SHA-1 is `d6b82f955a7beb9589f92e9487c74669d1912a34`. Only the single regular
`afg.csv` member is extracted, within a 512 MiB bound and an isolated directory.
The extracted CSV receives its own SHA-256 receipt and exact-byte checkpoints.

This source uses a different CSV dialect from Cablegate and mixes GUID and
legacy numeric and shortened hexadecimal report keys. These are treated as
opaque identifiers, not required to be UUIDs. The full Summary field is
preserved verbatim as the readable narrative; all other fields remain in the
normalized source record. Empty narratives stay in the original transport and
rejection ledger. Mirrored narratives have not been checked against every
publisher page or its redactions, so new records remain pending review.

Bulk import connections use SQLite WAL with NORMAL synchronization. A power
failure can lose a recent transaction tail; the committed checkpoint allows
idempotent replay against the retained, verified source. Normal application
connections retain their existing synchronization setting.

## Remaining release work

Each release still requires a file-level catalog, available transport checks,
storage estimate, checksums, original preservation, format-specific extraction,
deduplication and explicit gap accounting. Email archives must preserve
attachments and thread relationships. Scanned releases require OCR. Missing,
unavailable or encrypted files remain gaps rather than fabricated documents.
The current Cablegate adapter must not be reused blindly for different formats.
