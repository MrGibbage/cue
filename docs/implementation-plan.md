# Cue MVP implementation plan

This plan implements the agreed roadmap and [MVP acceptance exercise](mvp-acceptance.md). The first usable release is the safe, inspectable JSON-to-library-to-M3U workflow. Native providers are added behind the same discovery boundary and do not block that core flow.

## Progress

- **Milestone 0 — Foundation:** complete and verified with local tests and a
  Docker Compose smoke test.
- **Milestone 1 — Control plane:** complete and verified on the deployed Cue
  instance: administrator bootstrap/login, CSRF-protected collection creation,
  and collection retrieval work through `cue.pelorus.org`.
- **Milestone 2 — JSON discovery:** complete and verified on the deployed Cue
  instance: pasted JSON preview, immutable snapshot inspection, and explicit
  approval all succeeded.
- **Milestone 3 — Acquisition:** next.

## Delivery milestones

| Milestone | Deliverable | Exit gate |
| --- | --- | --- |
| 0. Foundation | Runnable application, worker, database, Compose | API/worker start; migrations and health checks pass. |
| 1. Control plane | Authenticated catalog, audit, durable jobs | Owner can create a collection and use a scoped token. |
| 2. JSON discovery | Paste/upload, validation preview, approval | Valid rows preview; nothing queues without approval. |
| 3. Acquisition | Candidate scoring, review, atomic publication | Only clear official videos auto-publish. |
| 4. Library import | Read-only scan, approval, reuse/de-duplication | Existing media imports idempotently and is reused. |
| 5. M3U and recovery | M3U8, reports, alerts, backup/restore | Exports, retry, Apprise, and restore are verified. |
| 6. Providers | Billboard feasibility and xmplaylist | Adapters create tested snapshots with provenance. |
| 7. Release rehearsal | Full staging acceptance run | The acceptance exercise completes without manual repairs. |

## 0. Foundation

- Create the Python 3.12 package, FastAPI app, Jinja dashboard shell, worker, and `cue-api`, `cue-worker`, and `cue-admin` CLI entry points.
- Make Dockerfile and Compose runnable from the existing deployment contract. The API retains a read-only media mount; only the worker gets writable media/staging access.
- Add typed startup configuration for database, media root, optional local download workspace, Apprise URL, cookies, token settings, and default batch size.
- Establish SQLite WAL, foreign keys, busy timeout, migrations, structured logs, `/healthz`, and `/readyz`.
- Add Ruff, pytest, type checking, and CI.

**Exit gate:** an empty database migrates cleanly; Compose starts both processes; readiness responds; the API cannot write media.

## 1. Control plane and data model

Implement the durable domain before external discovery or downloading.

| Domain | Entities |
| --- | --- |
| Access | users, roles, user_roles, sessions, api_tokens |
| Collections | collections, collection_versions, collection_entries |
| Source provenance | discovery_runs, source_snapshots, source_rows |
| Library | recordings, recording_artists, assets, asset_files |
| Resolution | collection_resolutions, candidate_assets, reviews |
| Work | jobs, job_attempts, rate_limit_state |
| Derived output | exports, export_items, backup_runs |
| Audit | audit_events |

- Recording identity is normalized artist credits plus normalized title; asset identity is distinct. Filenames are never the identity source.
- Keep snapshots immutable and audit events append-only. Include manual merge/override paths in the schema, though the dashboard may defer advanced management.
- Implement username/password login, secure sessions, CSRF protection, scoped tokens, and a separately scoped automation token. Persist token hashes only and show a token secret once.
- Put every mutation behind the versioned `/api/v1` service layer used by both dashboard and automation. Caddy and Cloudflare Access complement, rather than replace, application authorization.

**Exit gate:** the administrator can sign in, create/revoke a token, create a collection draft, and inspect audit events.

## 2. JSON discovery, preview, and approval

Support dashboard paste and `.json` upload. Accept either an array of entries or an object with `items` and source metadata.

```json
{
  "source": "Personal classic rock list",
  "items": [
    {
      "artists": ["The Clash"],
      "title": "Should I Stay or Should I Go",
      "rank": 1,
      "year": 1982,
      "album": "Combat Rock",
      "notes": "Original list order",
      "source_id": "classic-rock-001"
    }
  ]
}
```

- Require a non-empty `artists` array and `title`; permit `rank`, `source`, `source_url`, `notes`, `year`, `album`, and `source_id`.
- Retain unknown optional fields as raw provenance. Accept valid rows while reporting rejected rows with reasons.
- Preserve rank or array order. Detect canonical duplicates inside the collection, retain the first, and report the rest.
- Persist an immutable preview snapshot. Approval, not preview, creates durable jobs. Automation can create previews but must make a separate explicit approval call.
- Build collection editing, preview, snapshot inspection, approval, and run/job monitoring dashboard/API flows.

**Exit gate:** a 25-song list with deliberate invalid and duplicate rows produces the expected persisted preview and queues work only after approval.

## 3. Acquisition, review, and publication

- Worker claims jobs in short transactions, has a lease/heartbeat for crash recovery, and enforces the user-configured new-download batch size (initially 25) for each approved run.
- Define a provider interface for search, metadata, download, and errors. Implement yt-dlp first, with ffprobe validation and ffmpeg only when needed for the configured MP4/MKV outcome.
- Apply global YouTube-facing concurrency and token-bucket limits.
- Store each candidate's URL/ID, metadata, classification, component scores, explanations, uploader evidence, and runner-up margin.
- The strict default auto-selects only a clear official music video. Unclear, remaster/reupload, visualizer, lyric, live, cover, remix, karaoke, reaction, fan-made, shortened, and audio/static-art cases enter review; no acceptable candidate means unresolved.
- Model these as configurable user/collection preferences, retaining the strict music-television profile as default.
- Download to optional local workspace, copy into hidden same-filesystem media staging, validate, then atomically rename to configured flat or artist-directory layout. Default filename: `Artist - Title [YouTube ID].ext`.
- Never replace an asset automatically. Better/remastered replacements always require review.

**Exit gate:** fixtures prove a clear auto-selection, review hold, unresolved recording, bounded retry, failed validation, and no final partial file.

## 4. Existing library import and reuse

- Scan the media root read-only. Start with `Artist - Title (descriptor) [year].ext`, preserve originals, and report confident parses, ambiguities, unparseable files, and collisions.
- Support dry-run followed by explicit approval; make repeat imports idempotent. Add CSV mapping/manual resolution for exceptions.
- Before acquisition, match to existing imported/published assets and attach the asset to the collection rather than download it again.
- Globally de-duplicate recording and asset state; permit intentional alternates only via explicit variant/resolution records.

**Exit gate:** representative existing files import; a second import is a no-op; an imported matching asset is reused by a new collection.

## 5. M3U, alerts, and recoverability

- Generate deterministic UTF-8 `.m3u8` artifacts in collection order, using configured absolute or relative paths. Never write a nonexistent path; create a missing-item report instead.
- Expose export plans/downloads and persist export manifests/digests.
- Notify failed and review-needed work through self-hosted Apprise. Notification delivery failure is logged but never alters job state.
- Run daily SQLite online backups, keep 30 days, audit outcomes, and provide an explicit-path restore command.
- Let owners inspect and explicitly retry failed jobs; after a configured retry limit, they remain failed.

**Exit gate:** expected M3U8 and missing report match fixtures; Apprise payloads test successfully; backup restores to a separate test location.

## 6. Provider adapters

All adapters produce source snapshots and never download directly.

1. Time-box a Billboard feasibility spike: identify a stable, permitted data source and document the access/licensing basis. If unsuitable, defer the native adapter without blocking MVP core.
2. If viable, implement Billboard mapping for chart/date/rank/provenance.
3. Implement xmplaylist with Alt Nation as the reference station and station/window parameters for future expansion.

**Exit gate:** every included adapter converts saved provider fixtures to expected immutable snapshot rows and provenance.

## 7. Release rehearsal

Run [the acceptance exercise](mvp-acceptance.md) against a staging library. Preserve its import preview, source snapshot, candidate/review record, job history, media manifest, M3U8, missing report, notification receipt, backup, and restored test database. Fix any unexpected duplicate download, disallowed automatic selection, partial publication, unapproved work, or wrong export order/path before release.

## Test fixtures and verification

- Unit tests: schema validation, normalization, duplicate/order rules, scoring/classification, filename parsing, path containment, retry behavior, M3U rendering.
- Service/database tests: migrations, job claims/leases, approval transitions, de-duplication, audit events, tokens.
- Integration tests: dashboard/API flows, fake provider worker execution, atomic staging/publication, notifications, backup/restore.
- Keep tests independent of live providers using minimal saved fixtures. Perform real yt-dlp, NAS permissions, reverse proxy, Apprise, and player playback checks only in staging.

## Deferred work

- In-app LLM planning or candidate review.
- MVG-specific SQLite/history import.
- Unattended approval for scheduled automation.
- Plex and other native player publishers.
- Multi-user collaboration, PostgreSQL, multiple workers, a broker, and a SPA.
