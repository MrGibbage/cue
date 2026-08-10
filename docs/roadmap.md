# Cue roadmap

This is the living delivery roadmap for Cue. Decisions made during MVP planning
should be recorded here or linked from the relevant phase.

The detailed execution plan is [implementation-plan.md](implementation-plan.md).

## Delivery progress

- 2026-08-05: Milestone 0 foundation completed and Docker-verified.
- 2026-08-05: Milestone 1 control plane completed and verified through the
  deployed Cue instance.
- 2026-08-06: Milestone 2 JSON discovery completed and verified through the
  deployed Cue instance.
- 2026-08-06: Milestone 3 safe video acquisition completed and verified through
  the deployed Cue instance.
- 2026-08-06: Milestone 4 generic existing-library scan and approval import
  completed. Dedicated MVG catalog import remains deferred.
- 2026-08-06: Milestone 5 deterministic M3U8 export previews, approval, and
  missing-item reports completed. Notifications and backup/restore remain.
- 2026-08-06: Milestone 6 server-rendered dashboard and settings completed.
- 2026-08-06: Milestone 7 operational reliability implemented: verified daily
  backups, Apprise alerts, job recovery, and diagnostics. Deployment status is
  verified as part of each release, rather than inferred from implementation.
- 2026-08-07: Milestone 8 provider work implemented and staging-smoke-tested:
  the user-configured Billboard Hot 100 adapter and xmplaylist Alt Nation
  adapter preserve immutable raw captures and use normal preview/approval.
  Provider recipes support artist/title filtering, rank ordering, and limits;
  xmplaylist follows history pages through the requested lookback window.
- 2026-08-08: List-first intake hardening completed: paste, upload, and API
  JSON share a bounded document limit, persist preview outcomes, and cannot
  approve a list with no accepted songs.

## 1. Product decisions and acceptance specification

- Resolve MVP scope, source support, matching rules, acquisition policies,
  library naming, publishing behavior, deployment, and API priorities.
- Define representative fixtures: source snapshots, good and bad candidate
  matches, existing media, and MVG exports.
- Write measurable acceptance criteria for operating Cue alongside, then
  replacing, Music Video Grabber (MVG).

## 2. Project foundation

- Create the Python package, Dockerfiles/Compose stack, configuration
  validation, structured logging, Ruff, pytest, and CI.
- Implement SQLite initialization, WAL configuration, migrations, online
  backup/restore tooling, and health checks.
- Establish non-root containers and the read-only/read-write mount boundary.

## 3. Core domain and authentication

- Implement users, roles, sessions, scoped API tokens, automation-token
  handling, and secret-safe responses.
- Build schema and services for recipe versions, source snapshots, recordings,
  assets, collections, provenance, jobs, reviews, and publisher manifests.
- Define the OpenAPI contracts early so the dashboard and automation use the
  same control surface.

## 4. Discovery and preview workflow

- Make user-supplied JSON song lists the primary discovery contract.
- Add optional convenience adapters behind the same immutable snapshot,
  preview, and explicit-approval boundary.
- Build the preview -> approval -> durable-work lifecycle.

## 5. Acquisition worker

- Implement transactionally claimed SQLite jobs, retries, failure visibility,
  and global provider rate limiting.
- Integrate yt-dlp, ffprobe/ffmpeg validation, same-filesystem staging, and
  atomic media publication.
- Build deterministic search, classification, scoring, evidence display,
  policy thresholds, and candidate review.

## 6. Library management and migration

- Implement global recording/asset de-duplication and explicit alternate-video
  versions.
- Add dry-run, idempotent existing-library import with filename parsing, CSV
  mappings, and manual exceptions.
- Add the MVG importer with provenance and safeguards against re-queueing
  already published assets.

### Large-library hardening (required follow-up)

The initial generic importer is deliberately conservative and read-only, but
its preview scan is synchronous: it walks the configured media root, stores all
preview rows in one transaction, and returns all rows in one API response. It
is suitable for a normally sized personal library, but is not yet a reliable
web-request workflow for a library with roughly 10,000 or more files.

- There is no intended library-size cap: a flat directory with 10,000 videos is
  acceptable to the filesystem and SQLite.
- The concern is HTTP request duration, memory use, response size, and reverse
  proxy/client timeouts, not file safety or SQLite row capacity.
- 2026-08-09: Large-library import hardening completed: scans are durable
  background jobs with persisted progress, cancellation/failure visibility,
  bounded write batches, and an approval gate at successful preview completion.
- Import-preview rows and library search are paginated; APIs return counts and
  a page of rows rather than an unbounded full-library response.
- Expose directory-level progress and configurable safety limits so an operator
  can understand and control a long scan.

## 7. Publishers

- Implement deterministic M3U/M3U8 exports and unresolved-item reports.
- Implement Plex read-only planning, scoped apply to registered Cue playlists,
  rollback manifests, and recovery reporting.

### M3U8 delivery notes

- Cue persists an immutable export manifest from the collection's latest
  approved source snapshot. The manifest preserves resolved order and records
  every omitted item with a reason.
- An export is previewed before a separate explicit approval queues publication.
  The worker atomically writes a UTF-8 `.m3u8` artifact and a JSON
  missing-item report, then records a digest.
- `CUE_M3U_PATH_PREFIX` is optional. When set, each playlist entry is prefixed
  with the media-root path visible to the target player; otherwise entries are
  relative to Cue's media root. This keeps player-specific path mappings out of
  collection data.

## 8. Dashboard and operational polish

- Deliver the server-rendered flows for status, recipes, previews, review,
  library search, imports, publisher plans, and audit history.
- Add operational diagnostics for rate limits, failed jobs, validation failures,
  and missing Plex items.
- Document deployment, backup/restore, upgrade, and incident recovery.

### Dashboard delivery notes

- Cue's browser UI is server-rendered and uses the existing authenticated,
  CSRF-protected control plane rather than introducing a second mutation path.
- It includes sign-in, collection creation, JSON-list preview and approval,
  candidate review/selection, library-import scan/approval, M3U8 export
  preview/approval/download, and a persisted download-batch-size setting.
- Environment-owned settings such as `CUE_M3U_PATH_PREFIX` remain deploy-time
  configuration because they describe how a particular player mounts media.

### Operational delivery notes

- The worker creates a SQLite online backup once per UTC day, verifies it with
  `PRAGMA integrity_check`, and retains the configured 30-day window by
  default. `cue-admin restore` requires a new explicit destination and never
  overwrites an existing database.
- Notifications use the configured self-hosted Apprise endpoint on terminal job
  failures. Delivery is best-effort and never changes a Cue job outcome.

## 9. Verification and MVG cutover

- Run fixture-based unit/integration tests and a real staging-library trial.
- Rehearse migrations and compare Cue's xmplaylist capture, scoring, retries,
  de-duplication, and Plex behavior with MVG.
- Run Cue alongside MVG until the acceptance criteria are satisfied, then
  switch scheduled automation.

## Version 3 — library intelligence and safe rehabilitation

Version 3 follows MVP cutover work. Its first planned capability is a
read-only, review-driven library quality audit for identifying lyric videos,
visualizers/static-art uploads, and likely filename-to-recording mismatches.

- Run quality audits as durable, resumable background jobs with bounded
  evidence extraction and reuse for unchanged files.
- Combine inexpensive local media signals with optional OCR/vision analysis;
  sample frames rather than defaulting to frame-by-frame inference.
- Add an opt-in audio-identification adapter boundary and compare sufficiently
  confident returned recording identities against filename claims.
- Preserve immutable findings, evidence, model/provider configuration, and
  owner decisions. Present ranked review queues; never mutate media as a scan
  side effect.
- Share the resulting background-job, progress, cancellation, and pagination
  foundation with the large-library import hardening work.

The full proposal and acceptance criteria are in
[library-quality-audit.md](library-quality-audit.md).

## Next product workflow — guided new-library setup

Cue's core operations are implemented, but first-time setup currently spans
media-root deployment, optional existing-library import, JSON source preview,
approval, background work, candidate review, and export. The next product
workflow should make that sequence legible without adding a bypass around any
safety boundary.

- Add a resumable dashboard checklist for a new/test library versus an existing
  library, acquisition defaults, first JSON list, job/review progress, and
  export.
- Retain one active deployment-configured media root initially. A clean test
  run uses a separate Compose/data instance and an empty dedicated media root;
  it must not repoint the production database at an empty folder.
- Defer any reset/delete feature until Cue has root-bound ownership evidence.
  A future test-only reset requires a complete preview, verified backup, typed
  confirmation, durable job/audit trail, and can delete only Cue-owned media
  in that declared test root.
- Keep existing-library scanning read-only and all source/import/download/export
  approval gates intact.

The detailed product proposal and acceptance criteria are in
[new-library-setup.md](new-library-setup.md).

## MVP decision record

### Product direction — 2026-08-04

- Cue is not primarily an MVG replacement. Its success is measured against the
  product goals in this repository: a recipe-driven, inspectable personal
  music-video library with safe discovery, acquisition, and publishing.
- MVG is a useful migration and compatibility source. Cue should reuse and
  import what is valuable from it, without treating behavioral equivalence or
  an MVG cutover as a primary delivery goal.

### MVP discovery priorities — 2026-08-04

- The first end-to-end collection flow is structured JSON song input. Cue will
  publish a documented JSON format so that a user can create a list externally
  (including with a Codex prompt) and paste or upload it for preview and
  approval.
- Native Billboard chart discovery is an MVP priority and should be pursued as
  a provider adapter, subject to confirming a technically stable and permitted
  data-access method.
- xmplaylist is included initially with Alt Nation as the reference station,
  but Cue is not optimized around SiriusXM-specific behavior.
- MVP success includes importing an existing library, creating a new collection
  from an approved source, reviewing uncertain matches, safely publishing to
  Plex and M3U, and rerunning without unintended duplicates.

### List-first discovery direction — 2026-08-08

- Cue is for creating a themed, inspectable music-video collection from a song
  list the user brings. The list may come from personal research, a spreadsheet,
  an external AI, or any other source that can produce Cue JSON.
- The structured JSON import and preview/approval lifecycle are the core
  product path and should remain robust independently of any native source.
- The user-configured Billboard-compatible adapter and xmplaylist adapter are
  optional conveniences. They are not required inputs, do not define Cue's
  product scope, and must never bypass the normal immutable-snapshot review.
- Cue does not generate themed lists internally. The dashboard supplies a
  copyable JSON-only instruction for an external LLM; users remain responsible
  for reviewing the proposed list before approving it.

### JSON ingestion and LLM boundary — 2026-08-04

- Cue accepts song-list JSON both by dashboard paste and `.json` upload.
- Required fields are `artist` and `title`. The documented schema also permits
  optional `rank`, `source`, `source_url`, `notes`, `year`, `album`, and a
  source-specific identifier.
- JSON preview accepts valid rows and reports rejected rows; one invalid entry
  does not reject the whole import.
- Cue does not include LLM-based collection planning or natural-language list
  generation in the MVP. Users may create a list with an external LLM and
  import its structured JSON into Cue.
- Collections preserve submitted `rank`, or JSON array order when no rank is
  supplied. Preview detects duplicate desired recordings within a collection;
  the default retains the first occurrence and reports later ones.
- Global library de-duplication shares a published video asset across
  collections by default. Intentional alternate versions remain explicit
  collection-level choices.
- The default acquisition policy is **Careful automatic**: Cue downloads only
  near-certain matches and sends uncertain items to review. **Review
  everything** is available per collection.

### Default video-selection rules — 2026-08-05

- The normal collection outcome is an unambiguous official music video for the
  intended recording. Cue does not auto-acquire an official-channel upload
  whose format is unclear.
- There is no automatic fallback to a lyric video, visualizer, official audio,
  static album art, live performance, or other non-ideal asset. An item without
  an acceptable official music video remains unresolved and may be skipped.
- Covers, karaoke, reactions/commentary, fan-made videos, remixes,
  shortened/edited versions, and concert/live performances always require
  review, even when artist/title matching is strong.
- Remasters or official reuploads may be desirable when artist-authorized and
  higher quality, but always require a user decision; fan-made remasters are
  not acceptable.
- Audio-only and static-art assets are not acceptable in the normal music-video
  library: Cue should acquire assets that belong in a music-television
  experience.
- Video-selection preferences must be user-configurable (at least globally and
  per collection where applicable); the strict music-television rules above are
  the initial default, not a hard-coded limitation.

### Library publication rules — 2026-08-05

- The default published filename is `Artist - Title [YouTube ID].ext`.
- Flat and artist-subdirectory layouts are supported configuration choices; the
  initial default is a flat library layout.
- MP4 is the initial preferred container; MKV is acceptable as a configurable
  alternative.
- When an approved asset is already imported or published in the library, Cue
  links it to the new collection without downloading it again.
- Replacing an existing asset with a better/remastered version always requires
  user review and an explicit decision; it is never automatic.

### Initial publishing scope — 2026-08-05

- The first release publishes deterministic M3U/M3U8 exports and missing-item
  reports. Native Plex publishing is deferred while supported media-player
  targets are evaluated more broadly.
- Future Plex support must manage only playlists explicitly created or
  registered through Cue and never modify unrelated playlists.
- A published playlist mirrors the collection's resolved order exactly. Desired
  recordings without an approved/published asset are omitted and included in a
  missing-item report.
- Future Plex updates use a complete pre-change manifest, per-playlist locking,
  and a post-apply fingerprint. On a partial failure, Cue automatically makes a
  best-effort rollback only when it can prove the playlist still reflects its
  own attempted update. Otherwise, or if rollback fails, Cue stops, preserves
  the manifests, and presents a repair plan for review.

### Migration and operations — 2026-08-05

- Existing-library import is an MVP requirement: scan read-only, generate a
  classification preview, then import only on explicit approval.
- An MVG SQLite catalog exists and is available as a migration source, but a
  dedicated MVG importer is deferred. MVP delivers generic existing-library
  import first and does not optimize around MVG compatibility.
- Representative existing names follow `Artist - Title (descriptor) [year].mp4`.
  The importer should parse artist, title, optional descriptor, and optional
  year conservatively while retaining the original filename and reporting
  ambiguous results for review.
- Cue deploys through Docker Compose on the same host that mounts the NAS media
  directory.
- Cue uses hybrid staging: an optional local download workspace, followed by a
  hidden same-filesystem staging directory under the NAS media root and an
  atomic final rename. Direct download to NAS staging remains available where
  local disk is constrained.
- SQLite backups run daily through the online-backup mechanism, retain 30 days,
  and have a documented restore command.

### Access, automation, and failure handling — 2026-08-05

- Cue is deployed behind existing Caddy reverse-proxy routes, Cloudflare Tunnel,
  and Cloudflare Access controls.
- The MVP includes an authenticated external automation API so cron or another
  scheduler can start collection runs.
- The initial user experience supports one administrator account; the schema
  retains user/profile ownership and role data for later expansion.
- Jobs retry only up to their configured limit. Afterwards they remain failed
  until explicitly retried, with the desired recording unresolved rather than
  silently skipped or retried forever.
- Cue sends notifications for failed and review-needed work through a
  self-hosted Apprise service, configured as an outbound notification target
  (which may deliver email).

### Dashboard, API, and execution controls — 2026-08-05

- The MVP dashboard includes sign-in and health/status, versioned collection
  editing, JSON paste/upload and preview results, snapshot approval, job
  monitoring and candidate review, imported/published-library search, M3U
  generation/download with missing-item reports, and failed-job retry.
- Every collection run requires explicit preview and approval, including runs
  initiated through the automation API. Unattended external approval is a
  future option after the application has established reliability.
- JSON uses `artists` (plural) and `title` as its core song fields, allowing
  structured multiple performer credits.
- Cue has no collection-size cap. A user-configurable new-download batch size,
  initially 25 and exposed in Settings, limits each approved run.

### MVP acceptance scenario — 2026-08-05

The MVP is accepted when the following is demonstrably successful:

1. An existing flat MP4 library is scanned, previewed, and imported only after
   approval.
2. A user pastes or uploads an externally generated 25-song JSON list.
3. Preview reports accepted, rejected, and duplicate rows while preserving
   supplied order.
4. Following approval, Cue automatically acquires only clear official music
   videos and sends uncertain candidates to review.
5. Cue never automatically adds audio-only, fan-made, live, remix, or similar
   non-default assets; reviewed items may be selected or skipped.
6. Cue generates a correctly ordered M3U8 and a missing-item report.
7. Re-running the list neither downloads known assets again nor creates
   unintended duplicates; an intentionally failed job can be recovered only by
   explicit retry.
8. A daily SQLite backup and restoration into a test location are verified.

Decisions and acceptance criteria will be added here as they are agreed.
