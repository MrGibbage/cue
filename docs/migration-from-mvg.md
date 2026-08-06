# Importing an existing library and MVG history

## Media-library import

Cue scans configured media roots without changing files. A naming policy can
parse consistently named files into artist/title candidates, then report:

- confidently identified media for import;
- probable matches needing confirmation;
- unparseable files; and
- collisions with existing library records.

Users can choose a different filename pattern, upload a CSV mapping, manually
resolve exceptions, or import unmatched files as media records without a linked
recording. Import is idempotent and starts with a dry-run report.

### Generic importer delivered in Milestone 4

The first importer scans only Cue's configured media root and only considers
MP4 and MKV files. Hidden paths (including Cue staging directories) and
symlinks are skipped. It conservatively recognizes the established pattern:

`Artist - Title (optional descriptor) [optional year].mp4`

The preview is read-only. It reports `accepted`, `review`, and
`already_imported` rows; only accepted rows are imported when explicitly
approved. Approval rechecks that each file is still inside the configured media
root and unchanged, then records its relative path and metadata without moving,
renaming, copying, or modifying the video. An imported asset is reusable by
later collections, so Cue does not search/download it again.

Messy filenames intentionally remain review-needed rather than guessed. They
can be normalized outside Cue and scanned again, or handled by later CSV/manual
mapping work.

### Large libraries

Cue has no intended maximum number of managed videos, and a single flat
directory with 10,000 videos is a valid library layout. The initial importer
does not yet make that scale a reliable browser request, however: it currently
scans synchronously, persists the full preview in one transaction, and returns
all preview rows together. The scan remains read-only until approval, but a
large request may be slow or hit a proxy/client timeout.

Large-library hardening will move scanning into durable background jobs with
progress and cancellation, use bounded database writes, and paginate both
preview and library-search results. Until that work lands, import a very large
library in smaller directory-scoped passes or use a staging/test subset first.

## Music Video Grabber import

Cue should provide a dedicated MVG importer. It reads MVG's SQLite catalog and
optionally legacy `altnation-songs.json` history, maps known tracks/candidates/
published state into Cue's recording and asset model, and preserves provenance
that identifies MVG as the source system. It must not copy credentials, active
jobs, cookies, sessions, or Plex secrets.

The migration produces a report of imported, skipped, ambiguous, and failed
records. It is repeatable and never queues an already-published MVG item simply
because it was imported.
