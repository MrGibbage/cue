# MVP acceptance

Cue's MVP is accepted by demonstrating a complete, safe personal music-video
library workflow. The project is assessed against the product goals described
in this repository, not as a behavior-for-behavior replacement of Music Video
Grabber.

## Acceptance exercise

1. Scan an existing flat MP4 library in read-only mode. Present parse results,
   ambiguities, and collisions; import only after explicit approval.
2. Paste or upload a 25-song JSON collection created externally. Core entries
   use `artists` and `title`; optional provenance and ranking fields are
   accepted.
3. Preview the source snapshot. It reports accepted, rejected, and duplicate
   rows, and preserves the supplied rank or array order.
4. Approve the snapshot. Cue queues at most the user-configured download batch
   size (initially 25) and automatically acquires only clear official music
   videos under the Careful automatic policy.
5. Present uncertain candidates for review. Do not automatically acquire
   audio-only, static-art, fan-made, cover, karaoke, reaction/commentary,
   remix, shortened/edited, live-performance, visualizer, lyric-video, or
   unclear-format assets. The owner can select an appropriate reviewed asset or
   skip the recording.
6. Produce a deterministic, correctly ordered UTF-8 M3U8 export and a
   missing-item report for desired recordings without a published asset.
7. Repeat the same run. Cue reuses an existing approved/published asset where
   appropriate and creates no unintended duplicate asset or download. Force a
   job failure, confirm its retry limit is respected, then recover it only via
   explicit retry.
8. Verify the daily SQLite online backup and restore it into a separate test
   location.

## Required operational behavior

- Collection runs always use preview followed by explicit approval, including
  when initiated through the authenticated automation API.
- The dashboard provides sign-in/status, collection editing, source preview and
  approval, job monitoring, candidate review, library search, M3U export,
  missing-item reporting, and failed-job retry.
- Failed and review-needed work sends notifications through the configured
  self-hosted Apprise target.
- Media publication uses a same-filesystem staging area under the configured
  media root and atomic final publication. A local download workspace may be
  used before that final staging step.
