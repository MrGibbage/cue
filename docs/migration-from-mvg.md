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

## Music Video Grabber import

Cue should provide a dedicated MVG importer. It reads MVG's SQLite catalog and
optionally legacy `altnation-songs.json` history, maps known tracks/candidates/
published state into Cue's recording and asset model, and preserves provenance
that identifies MVG as the source system. It must not copy credentials, active
jobs, cookies, sessions, or Plex secrets.

The migration produces a report of imported, skipped, ambiguous, and failed
records. It is repeatable and never queues an already-published MVG item simply
because it was imported.
