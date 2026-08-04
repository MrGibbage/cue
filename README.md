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
and [branding notes](docs/branding.md). The included `compose.example.yml` is
the deployment/mount contract, not yet a runnable stack: application entry
points will be added with implementation.
