# Readable titles and short source briefs

The archive keeps original titles and original bytes. Display aliases and briefs
are stored separately, with exact source page/character references.

Jev is a decisions model, not a prose generator. One call per document asks it
to approve a source-derived readable title and select a representative short
excerpt. The UI explicitly labels these as extractive source briefs. Later
updates or conclusions are retained alongside an initial account. Low-confidence
choices keep the original title and are marked for editorial review.

The selection considers up to three pages: two informative pages among the
first 25, plus the last page. Exact sampled pages, excerpts and omitted-character
counts are recorded. A brief is not a claim to have summarized every page or
verified the source's assertions. Nothing from source text is executed.

Run `python -m archive.library_cli enrich-documents --limit 1000 --collection wikileaks --include-unpublished --follow-imports`
only with authorization to send these excerpts to TypeSafe/Jev and incur API
charges. This local deployment's user explicitly approved all imported WikiLeaks
documents in batches of up to 1,000, including records awaiting publication review.
`--include-unpublished` applies only to WikiLeaks; it cannot disclose unpublished
records from other collections. Credentials stay server-side.

Results are saved after each document. Re-running skips the current editorial
version's completed assessments. The follow mode picks up new imports, stops
when no work or active incomplete imports remain, and pauses if imports have
not advanced for 15 minutes. API failure stops the worker while retaining results.
Title/brief processing does not publish an unpublished document.

Collection coverage reports assessed documents, accepted title-and-brief
selections and remaining imported documents. Saved progress alone does not prove
that a worker is currently running. Document cards and the reader show saved
results; documents awaiting Jev show a clearly labeled source-excerpt preview.

Provider contract: https://docs.typesafe.ai/introduction and
https://docs.typesafe.ai/primitives/choice.
