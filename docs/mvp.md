# MVP plan

## Included

1. Single-owner login with administrator role(s), user/profile foreign keys in
   the data model, scoped personal API tokens, and an external automation API.
2. Versioned collection recipes, discovery previews, source snapshots, and an
   explicit approval step.
3. CSV/JSON and xmplaylist discoverers. Assess Billboard feasibility early;
   exclude it from the MVP if no stable, lawful source adapter is available.
4. SQLite catalog, durable queue, candidate scoring, review, retries, global
   YouTube rate policy, stream validation, and atomic media publication.
5. Existing-library import, including consistent-filename import and MVG
   history/database import.
6. Global recording/asset de-duplication with explicit alternate-version
   support.
7. Guarded Plex playlist publishing and M3U/M3U8 export with missing-item
   reports.

## Deferred

- Conversational collection planning and advisory LLM candidate review.
- Soundcharts and other provider integrations.
- In-app scheduling.
- General multi-owner collaboration and sharing.

## MVG-replacement acceptance criteria

Cue may take over Alt Nation only after it can:

- capture and preserve the same xmplaylist recent-play snapshot semantics,
  including the Alt18 ranking inference when appropriate;
- produce equivalent candidate scoring, review, retry, duplicate, validation,
  and rate-limit behavior;
- import existing MVG library/history without re-queueing published videos; and
- perform Plex playlist planning, scoped apply, and rollback safely.
