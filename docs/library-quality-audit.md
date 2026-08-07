# Library quality audit proposal

## Purpose

Cue’s library quality audit is a read-only, evidence-driven rehabilitation pass
for an existing personal music-video directory. It helps an owner find files
that do not belong in the intended music-video library, including lyric videos,
visualizers, static-art uploads, and recordings whose audio appears not to
match the artist/title claimed by the filename.

It is designed for a one-time scan of a library such as an 800-video
collection, followed by occasional scans of only new or changed files. It is
not a cleanup bot: no file is renamed, moved, deleted, or imported as a result
of an audit unless the owner explicitly approves a separate action.

## Operator workflow

1. The owner starts a **Library quality audit** for a configured media root.
   The request creates a durable background job and records the scan settings.
2. Cue fingerprints every inspected file by path, size, modification time, and
   a content digest. Unchanged files with a completed audit are reused; changed
   files are scanned again.
3. Cue extracts low-resolution evidence locally: ffprobe metadata, a bounded
   set of scene-aware frames, and a short audio segment. Sampling—not
   frame-by-frame inference—is the default.
4. Local heuristics and, when configured, a vision/OCR model classify likely
   lyric, visualizer, static-art, live, and ordinary music-video signals.
5. An optional, explicitly configured audio-identification provider receives
   only the minimum required fingerprint or sample according to that
   provider’s documented terms. Cue compares the returned recording identity
   with the parsed filename identity.
6. The dashboard groups findings into review queues. The owner sees the
   filename claim, suggested actual recording, confidence, reasons, and saved
   evidence before recording a decision.
7. Owner decisions are durable: accept the file, mark its type, correct the
   claimed recording, exclude it from future scans, or queue a separate,
   explicitly approved library action.

## Classification and evidence

The scan produces independent findings rather than one opaque score:

| Finding | Typical evidence | Default outcome |
| --- | --- | --- |
| Likely lyric video | OCR detects persistent/changing lyric text across samples | Review |
| Likely visualizer/static art | Low scene-change/motion plus waveform, album art, or abstract graphics | Review |
| Possible wrong recording | Audio identity conflicts with parsed filename artist/title | High-priority review |
| Possible alternate version | Audio identifies the same recording family but a live/remaster/edit variant | Review |
| Identity unavailable | No confident audio identification or filename parse | Review only when other signals warrant it |

Evidence must make a decision inspectable: timestamps and hashes of sampled
frames, OCR snippets, visual-classifier reasons/confidence, audio-provider
response, comparison result, and the exact model/provider configuration. Raw
source responses and audit results are immutable once a run finishes.

## Accuracy and safety rules

- A visual or audio model is advisory. It must never automatically delete,
  rename, quarantine, or replace media.
- Official videos can contain lyrics, static sequences, visualizer-like motion,
  dialogue, or alternative edits. These are always presented as review
  evidence, not as facts.
- Audio identification may fail for intros, dialogue, live performances,
  edits, covers, or catalog gaps. An unmatched fingerprint is not proof that a
  filename is wrong.
- The comparison labels a mismatch only when both the filename parse and audio
  identity have sufficient confidence. Ambiguous artist credits and shared
  titles remain review items.
- Evidence thumbnails and clips use bounded size/retention settings. The
  original media stays in place and is read-only during scanning.
- External audio or vision services are opt-in and disclose what leaves the
  host. A local-only mode remains useful for visual triage and does not require
  external credentials.

## Technical outline

- Run scans as durable jobs with progress, cancellation, bounded batches, and
  directory-level status. This shares the large-library hardening required for
  library import scans.
- Use ffprobe and ffmpeg for metadata and evidence extraction. Start with
  8–16 sampled frames per normal-length video, plus scene changes or more
  samples only for uncertain results.
- Use inexpensive local features first (duration, motion, scene cuts, static
  frames). Invoke OCR/vision only for candidates or when the owner enables a
  configured model.
- Normalize parsed filename and returned audio identities with Cue’s existing
  recording canonicalization, while retaining the original values and provider
  response as provenance.
- Store audit runs, file observations, immutable findings, evidence references,
  and owner decisions separately from `published_assets`. The audit can assess
  unmanaged existing files as well as Cue-managed assets.
- Audio identification is an adapter boundary. Candidate integrations must be
  evaluated for accuracy, privacy, authentication, rate limits, and permitted
  personal-library use before Cue supports one.

## Acceptance criteria

1. A scan of roughly 800 videos completes as a background job without a
   request timeout and can resume/reuse unchanged file observations.
2. Fixture videos or saved evidence produce expected lyric/visualizer/static
   art and ordinary-video review classifications without live-network tests.
3. A mocked audio-identification response that conflicts with a parsed
   filename produces a high-priority mismatch finding and preserves its full
   provenance.
4. Every dashboard decision is audited and no media mutation occurs during the
   scan or review flow.
5. Re-running an unchanged audit does not repeat expensive analysis, while a
   changed file receives a new immutable observation.

## Non-goals for the first release

- Frame-by-frame AI inference by default.
- Fully automatic cleanup, rename, delete, or quarantine.
- Treating any third-party recognition result as authoritative.
- Replacing Cue’s normal, explicit approval process for actual library changes.
