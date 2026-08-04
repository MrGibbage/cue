# Product design

## The model

Cue is one application with distinct internal responsibilities:

```text
Discoverers -> desired-recording catalog -> acquisition queue -> library -> Plex/M3U
                         ^                      |                   |
                         +----------------------+-------------------+
                                      dashboard, preview, review
```

Discoverers create desired recordings with provenance; they never download
video. The acquisition layer searches, scores, reviews, downloads, validates,
and atomically publishes a selected video asset. A global rate policy governs
all YouTube-facing work.

The library stores a published video asset once by default, even where several
collections include its underlying recording. Collections retain their desired
membership, ordering, and resolution status separately. This means a playlist
can accurately show both what was requested and what has actually been
published.

## Users and authorization

The MVP serves a single owner through a simple username/password login, with
one or more administrator accounts. Database entities should nonetheless carry
an owning profile/user ID from the start, and roles should be data rather than
hard-coded assumptions. This allows multi-user behavior later without a data
migration that redefines ownership.

Dashboard sessions and personal API tokens are scoped to a user. The service
also has an automation token for externally scheduled calls. Secrets are never
returned after creation and only hashes are persisted where possible.

## Discovery and provenance

Initial discoverers:

- CSV/JSON imports;
- xmplaylist recent plays, parameterized by station and requested window; and
- a Billboard adapter if a viable, lawful, stable source can be established.

Each discovery run records the adapter, source identifier, retrieval time,
source fields such as date/rank/region, and the exact recipe version that
admitted the result. A preview creates an immutable source snapshot and a dry
run count/sample before approval enqueues acquisition.

Provider adapters for paid or free services, including a potential Soundcharts
integration, use the same boundary. A provider answers which recordings belong
in a collection; it does not decide which YouTube asset is correct.

## Recording identity and video identity

A desired recording and its video asset are distinct entities. For example,
`Van Halen — Jump` can have an official studio-recording video containing live
concert imagery, a remaster upload, a live performance, and lyric videos. The
default selection should be the official music video of the studio recording;
concert footage in that official video is acceptable.

Candidate scoring remains deterministic and explainable. It combines canonical
artist/title similarity, channel/uploader signals, title terms, duration, and
positive or negative classifications such as official, live, lyric, cover,
reaction, karaoke, remix, audio-only, and visualizer. The score, reasons, and
runner-up margin remain visible.

Global de-duplication is the default: one published asset per canonical
recording. A collection can opt into intentional variants, such as an official
video plus a lyric version or a live-performance collection. Recording identity
and asset identity are deduplicated separately so that this is explicit rather
than accidental.

## Simple matching controls

Library defaults and per-collection overrides should be framed in outcomes:

| Video preference | Intended result |
| --- | --- |
| Official music videos | Prefer an official video for the studio recording. |
| Official video, flexible format | Allow official visualizers, remasters, and live videos as fallbacks. |
| Sing-along | Prefer lyric videos and on-screen lyrics. |
| Live performance | Prefer official or high-quality live performances. |
| Custom | Expose allowed/disallowed categories and fallback ordering. |

The acquisition decision is a separate effort/risk choice:

| Policy | Behavior |
| --- | --- |
| Careful | Auto-acquire only extremely clear matches; review the rest. |
| Balanced | Auto-acquire clear matches; review uncertain ones. |
| Hands-off | Acquire reasonable matches with a complete audit trail; accept occasional odd results. |
| Review everything | Do not acquire until a person selects a candidate. |

Advanced users can tune score thresholds and margins. All modes preserve the
candidate evidence and allow a published selection to be replaced later.

## Publishers

Plex playlists are derived views. Updates are explicit, dry-run first,
rollback-manifest protected, and limited to designated Cue-managed playlists.
They never alter Plex media metadata, library settings, or unrelated playlists.

An M3U publisher creates UTF-8 `.m3u8` files usable by VLC and similar players.
Exports may use absolute configured-media paths or relative paths. They are
deterministic, replaceable build artifacts, accompanied by a report of desired
items that are still unresolved or unpublished.

## APIs and future LLM assistance

The deterministic API exposes recipe creation, source preview, approval,
acquisition monitoring/review, library search, and publisher plans/applies.
External scheduling remains outside the application and calls this API.

LLM assistance is post-MVP. It is a planning and advisory layer over those
same APIs, not an autonomous downloader. It may call tightly scoped read-only
tools such as a recent-play preview, supported-discoverer list, or catalog
search, then propose a recipe and source preview for explicit approval.

For candidate review, an optional user-configured LLM receives minimal,
structured candidate data and gives a recommendation, classification, and
confidence. Default policy lets it support review or corroborate a strong
deterministic match. A hands-off owner may opt into an LLM contribution to
automation, but the model identity, input summary, response, and final
decision must be auditable. It has no direct download, filesystem, or Plex
write capability.
