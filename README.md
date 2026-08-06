# Cue

Cue is a personal music-video library builder. It turns curated rules and
external music data into a durable, inspectable local video library, with
optional Plex playlists and VLC-compatible M3U exports.

It is designed to replace the Alt Nation-specific workflow of Music Video
Grabber once it has proven the same capture, acquisition, and publishing
safeguards.

## Product principles

- A collection is a versioned recipe, not a hard-coded genre or station.
- Discovery selects desired recordings; acquisition selects video assets.
- The library deduplicates globally by default while allowing intentional
  alternate video versions when a collection opts in.
- Matching is explainable, reviewable, and safe to run over time.
- Plex and M3U are derived publishers, never the source of catalog state.
- External callers and future conversational interfaces use the same preview,
  approval, and queue APIs as the dashboard.

## Initial scope

The MVP supports CSV/JSON uploads, SiriusXM recent-play discovery through
xmplaylist, and a Billboard adapter only if its data source proves viable. It
includes durable acquisition, library import, Plex/M3U publishing, and a
single-owner dashboard. LLM-assisted planning and candidate review are planned
immediately after the MVP, not inside it.

Read [the product design](docs/product-design.md), [MVP plan](docs/mvp.md),
[migration plan](docs/migration-from-mvg.md), [technical design](docs/technical-design.md),
and [branding notes](docs/branding.md). The runnable Compose stack is in
`compose.yml`; `compose.example.yml` remains the original deployment/mount
contract.

## Development foundation

Milestone 0 provides a runnable API and worker foundation. With Python 3.12,
install development dependencies with `pip install -e '.[dev]'`, then run
`pytest` and `ruff check .`.

For a Compose smoke test, use an existing writable directory as a temporary
media root and an unused local port. Run this from the Cue repository (where
`compose.yml` lives):

```sh
cd /srv/cue
CUE_ENV_FILE=/dev/null CUE_MEDIA_DIR=/path/to/test-media CUE_PORT=18080 docker compose up --build
```

The temporary foundation interface is available at `/`; health endpoints are
`/healthz` and `/readyz`, and FastAPI documentation is at `/docs`.

## Milestone 1 setup

Before the first production startup, add a long unique `CUE_SESSION_SECRET` to
the root-readable file referenced by `CUE_ENV_FILE`. To create the first
administrator, also add `CUE_BOOTSTRAP_ADMIN_USERNAME` and
`CUE_BOOTSTRAP_ADMIN_PASSWORD` for that first startup; Cue hashes the password
and creates the account only when no user exists. Remove the bootstrap password
from the file after the account has been created.

The initial control-plane API is available at `/docs`. Sign in through
`POST /api/v1/auth/login`; its response contains the session CSRF token required
for session-authenticated mutations. You can then create a collection draft,
create/revoke a scoped API token, and inspect your audit events through the
`/api/v1` endpoints.
