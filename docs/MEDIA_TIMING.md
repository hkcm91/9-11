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
