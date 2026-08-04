# Technical design

## MVP stack

- Python 3.12 or newer.
- FastAPI for the authenticated dashboard, deterministic API, health checks,
  and OpenAPI schema.
- Server-rendered Jinja templates with small, purpose-built browser JavaScript.
  A separate SPA is not an MVP requirement.
- SQLite in WAL mode, accessed by one API process and one acquisition worker.
- yt-dlp plus ffmpeg/ffprobe for candidate metadata, download, and stream
  validation.
- Docker Compose for deployment; pytest and Ruff for verification.

Cue starts as a single-owner application with one acquisition worker. Its data
access and ownership model must not preclude a later PostgreSQL or multi-worker
deployment, but neither is a reason to introduce a database service or queue
broker before the MVP needs one.

## Process model

The API process authenticates users, serves the dashboard/API, creates durable
work, previews source data, and plans publishers. It does not download or write
media.

The worker claims durable SQLite jobs and performs discovery, candidate search,
scoring, optional review handling, download, validation, and publication. One
worker makes rate limits, NAS writes, and job ownership easy to inspect. It
enforces global per-provider and YouTube-facing concurrency/token-bucket limits.

External cron or systemd timers call the API for scheduled collection runs.
Cue has no in-app scheduler in the MVP.

## Database and storage

SQLite is configured for WAL mode with transactionally claimed jobs. Application
backups use SQLite's online backup API, never a raw copy of the database and
WAL files. The initial schema includes profile/user ownership foreign keys and
role data even though the MVP has only one owner and administrator accounts.

There is one configured media root in the MVP. Every collection output path is
validated as a relative subdirectory beneath it. The worker's hidden staging
directory lives on the same filesystem as that media root, allowing atomic
publication with a rename/replace operation.

## Containers and mounts

```text
cue-api       source/config read-only; database writable; media read-only
cue-worker    source/config read-only; database writable; media and staging writable
```

Both services run as a configurable non-root host UID/GID, normally the owner
of the NAS-mounted media directory. Neither service gets the Docker socket.
The API must never have a writable media mount. Source-provider credentials,
cookie files, and future LLM credentials are host-managed secrets, mounted
read-only or supplied through a root-readable environment file; they are not
committed to Git or saved in API responses.

Recommended production layout:

```text
/srv/cue/                         Git checkout and Compose project
/srv/cue/data/                    SQLite state and online backups
/etc/homelab/cue.env              Service configuration and secrets
/etc/homelab/cue.cookies.txt      Optional YouTube cookies
/mnt/nas/media/Music Videos/      Configured published-media root
```

## Operational interfaces

The OpenAPI API is the shared control surface for the dashboard, command-line
automation, external schedulers, and later LLM planning tools. Its lifecycle is
always preview -> explicit approval -> durable work -> review/monitoring ->
publisher plan -> explicit apply. An LLM is never granted a special write path.

Plex writes remain an explicit operation against named Cue-managed playlists,
with a read-only dry run and rollback manifest. M3U/M3U8 generation is a
replaceable derived artifact and reports unresolved desired recordings.

## Deliberately deferred

- PostgreSQL and multiple concurrent acquisition workers.
- A message broker or background-task framework.
- A React/Vue single-page application.
- In-app schedules.
- Database-stored, per-user encrypted provider credentials.
- Published container images; production initially builds from the checked-out
  repository with Docker Compose.
