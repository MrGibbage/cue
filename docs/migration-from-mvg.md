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
directory with 10,000 videos is a valid library layout. Starting a scan creates
a durable queued job and returns immediately. The worker scans read-only,
stores rows in configurable bounded batches (`CUE_LIBRARY_SCAN_BATCH_SIZE`,
default 250), and persists files/directories inspected plus the current path.
The dashboard and API show queued, scanning, previewed, failed, or cancelled
states; preview rows and library search are paginated. Approval is unavailable
until a scan reaches `previewed`. Cancelling or failing a scan never imports or
modifies media.

## Music Video Grabber import

Cue should provide a dedicated MVG importer. It reads MVG's SQLite catalog and
optionally legacy `altnation-songs.json` history, maps known tracks/candidates/
published state into Cue's recording and asset model, and preserves provenance
that identifies MVG as the source system. It must not copy credentials, active
jobs, cookies, sessions, or Plex secrets.

The migration produces a report of imported, skipped, ambiguous, and failed
records. It is repeatable and never queues an already-published MVG item simply
because it was imported.
