# Media population and Jev timing review

The manual `phase0-scale` workflow accepts expanded photo-map, NIST and Internet
Archive limits, plus `jev_timing_limit` (default 0; maximum 500). It collects
source-hosted image/video records and preview links, builds the SQLite database,
then optionally uses the existing TypeSafe repository secret for a bounded Jev
audit. It does not copy or republish the media binaries.

Jev evaluates whether actual source metadata supports the proposed time kind,
interval and precision. Samples rotate across source and timing method. Decisions
and their full evidence context are saved in `reports/jev-timing-decisions.jsonl`;
eligible proposals are inserted into `agent_proposals` for review. Claims are
never verified or rewritten by Jev. A support answer is not independent historical
corroboration and its confidence is not timestamp accuracy.

archDisk ranges such as `8:46-9:03AM` become broad curator-attributed capture
intervals on September 11 in America/New_York (EDT). Minute-only notation spans
the stated minute, second notation spans the stated second; neither establishes
camera-clock calibration. Before/after bins remain open-ended. Impact/collapse
category labels do not manufacture exact event timestamps. Unknown times stay
unknown. Internet Archive recording intervals remain distinct from capture times
because broadcast footage may be a replay. NIST hierarchy entries without timing
metadata are retained without a timing claim.

Frame-level synchronization still requires the original recording, identifiable
reference frames, independently established event anchors, and clock/offset
uncertainty. This metadata review does not pretend to inspect video or images.

Existing databases retain their old claims. Rebuild derived claims into a fresh
database to use the improved precision handling; do not silently replace reviewed
claims in a previously reviewed database.

## NIST anchor ordering pilot

`python -m evidence_collections.september11.anchor_ordering --database archive.sqlite
--output reports --jev` builds attachment-level minute candidates and reviews a
small, visually inspected pilot with Jev. The optional `archive_run_id` input on
`jev-live-smoke` reuses a completed `phase0-scale-corpus` artifact, avoiding a new
crawl. No model credentials are exported.

The checked-in anchor catalog records the report URL, PDF and printed page,
figure, displayed time, clock basis, creator, observations, source image URL and
image SHA-256. Five inspected figures from NIST NCSTAR 1-5A are included. Two
Sean Adair attachments appear to match figures 7-5 and 7-8; these remain proposed
visual matches. Their reported minutes are 09:03 EDT. The other inspected images
support sequence proposals but not inferred equal spacing or fabricated times.

NIST section 3.6 (PDF page 119) explains the five-second adjustment between its
original database and precise reported times. The catalog uses published adjusted
figure labels without applying the correction twice. Figure 7-5's integer label
and fractional impact-relative caption are both retained instead of silently
reconciling rounding. Per-image uncertainty not printed in a caption remains
unknown; the report's overall three-second accuracy statistic is not inherited.

`reference_image_anchors`, `media_minute_candidates` and
`anchor_ordering_decisions` are separate research tables. No source metadata,
capture claim, or review status is overwritten. The JSON export labels candidates
as source-reported minute, broad range, group timing only, broadcast interval only,
open bound, unknown, or proposed anchor match. Multiple images under one record
never automatically inherit an individual capture time. Jev sees the documented
visual observations as text; it does not inspect image pixels in this pipeline.

This is a partial ordering, not a verified total ordering of the collection.
More independent image matches, calibrated camera series, or continuous timed
video are needed to narrow broad intervals. The source files remain hosted by
their custodians and are not included in the code or output package.

### Explorer ordering panel

The Explorer ships a frozen pilot overlay in `apps/web-explorer/ordering.json`, derived from `minute-ordering.json` in Jev run 35469627152 against corpus run 35468462018. It preserves 3,198 individual asset IDs, five NIST references, two proposed sequences, and the Jev review results. Capture/recording claim copies are omitted from this overlay; the existing Explorer source records retain their time and location claims.

The minute selector joins assets to the current map by parent ID and includes only source-reported minutes within the map window (78 of 80 in the pilot 08:00–12:00 window). Uncertain matches and broad ranges never become minute assignments. Sequence buttons open the chosen attachment at its parent camera location. A selected reference outside the filters remains visible with an explicit inspection label. NIST figures link to the original PDF pages and do not get invented map coordinates.

Both Pages deployment and the scale artifact package the overlay. It is a versioned pilot, not an automatically refreshed analysis; unmatched parent IDs cannot navigate to a map record. External media remain hosted by their sources and may load slowly or be unavailable.
