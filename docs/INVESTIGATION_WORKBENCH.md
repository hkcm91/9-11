# Editorial review and investigations

The local archive has two additional sidebar views:

- Editorial review: filter uncertain Jev assessments, OCR gaps, or unpublished
  documents. Inspect source pages, edit the reading title and brief, then save a
  reasoned decision, defer the record, or reopen it. Every save appends history;
  stale concurrent edits are rejected. Human-reviewed wording takes precedence
  over later Jev output. Original bytes and titles remain unchanged. This action
  does not publish a document or resolve its underlying OCR flag.
- Investigation folders: create a guiding question, save source pages from the
  reader, and collect exact quotations, reporting notes, open questions,
  alternative hypotheses, and dated timeline entries. Mark items handled or
  reopen them. Export a Markdown evidence packet with page citations and original
  hashes. Hypotheses and source assertions are not represented as verified facts.

Select text in the source reader before choosing **Save to investigation** to
prefill an exact quotation. Quotes must match the cited page and identify one
unambiguous occurrence. Folder citations require a published source. Withdrawing
that source hides its associated item text and citation in both folder views and
exports, while retaining the underlying record for audit.

These views are for the loopback operator workspace. Mutations require the
existing same-origin request protections; review reads also require a loopback
Host. They introduce no model calls or publication changes. Multi-user identity
and access controls remain outside this local application's scope.

Storage: `library_editor_reviews`, `library_folders`, and `library_folder_items`
in the existing local database. Review text is explicitly labeled human-edited
and is not presented as an exact Jev-selected quotation.
