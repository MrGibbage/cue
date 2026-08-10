# New-library setup and test-workspace proposal

## Status

**Proposed; no implementation yet.** This document describes the next
product-facing workflow after the core list-to-video lifecycle. It does not
change Cue's current single configured media root or delete any media.

## Problem

Cue's individual operations are intentionally safe, but a person creating a
library must currently connect several separate concepts:

1. choose a physical media directory;
2. decide whether it contains an existing library or is a fresh destination;
3. bring a song list and approve an immutable snapshot;
4. watch matching/download work and resolve uncertain videos; and
5. publish an export.

That is appropriate for an operator, but it makes experimentation feel
irreversible. In particular, a temporary incoming/test folder needs to be
visibly different from a real library, and reset must never be confused with
an existing-library scan.

## Product decision

Introduce a resumable **New library setup** checklist in the dashboard. It is
a guide and a stateful record of user decisions, not a privileged alternate
pipeline. Every mutation continues to use the normal preview, explicit
approval, durable-job, and review controls.

The first version should retain one active, deployment-configured media root.
Multiple simultaneous media roots are a later capability, not an accidental
side effect of the wizard. For a clean test run today, operators should use a
separate Compose/data instance and a dedicated, empty media directory rather
than point the production database at a different folder.

## Proposed flow

### 1. Choose and verify the destination

The opening screen identifies the active physical root, its free space, and
whether the worker can create and remove a private verification file there.
It labels the destination as one of:

- **New/test library** — an intentionally empty, dedicated folder;
- **Existing library** — contains media that Cue must only scan and import;
- **Continue setup** — a prior setup record already exists.

The label is a safety declaration, recorded in audit history. It does not make
an arbitrary non-empty directory safe to delete.

### 2. Select the starting path

The setup offers two mutually exclusive paths:

- **Start fresh**: no import scan. The page makes clear that approved Cue
  downloads will be published into the active root.
- **Bring an existing library**: starts the current durable read-only scan,
  shows its progress, and permits import only after the scan reaches
  `previewed`.

The existing-library path must retain current rules: scan/import never moves,
renames, copies, or deletes a source file; cancellation and failure never
import media.

### 3. Set acquisition defaults

The user confirms a conservative policy before the first list:

- Careful automatic matching is the default.
- Only high-confidence, correct-song official-video candidates can be queued.
- Uncertain, alternate, live, lyric, cover, audio, and wrong-song candidates
  stay in review.
- The first run has a visible download limit, with the existing setting as the
  authoritative value.

The page explains that candidate selection and publication are separate. It
shows where channel trust and video-quality preferences will live once those
controls are implemented.

### 4. Bring the first list

The wizard leads directly to the existing JSON paste/upload preview and its
copyable JSON-only prompt. It presents source preview results before approval:

- accepted, rejected, duplicate, and rank outcomes;
- the immutable snapshot identifier and source provenance; and
- the exact count that approval will queue.

There is no automatic approval. The normal **Approve & queue** action remains
the sole transition to matching work.

### 5. Monitor, review, and finish

A single progress page aggregates the normal job states:

- queued/scanning/resolving/downloading/completed/failed/cancelled;
- counts for published, existing/reused, review-needed, and failed items; and
- links to the jobs table and collection review decisions.

Completion means all automatically eligible work has settled, not that every
desired song has a video. The final step leads to the normal M3U8 preview and
explicit publish action.

The checklist is resumable and may be dismissed after the user understands the
workflow. It must never block expert access to existing dashboard pages.

## Test workspace and reset model

The product needs two distinct operations, with deliberately different safety
boundaries.

### Create a test workspace

This is deployment setup, not a dashboard folder picker in the initial
version. A test instance gets:

- a dedicated empty media root, separate from the real library;
- a separate SQLite data directory/Compose project; and
- the same worker staging and atomic-publication checks as production.

Separating both files and database state is important. Repointing a production
database at an empty test directory makes existing `PublishedAsset` paths look
wrong and can hide the difference between reuse and a new acquisition.

Future multi-workspace support may make this a dashboard feature, but only
after each workspace has an explicit root, ownership model, storage quota, and
independent audit boundary.

### Reset a test workspace

Reset is a future, test-only operation—not a normal collection action. It
must first produce a preview listing every database record and file affected.
It must require an explicit typed confirmation containing the workspace name.

The reset scope is intentionally narrow:

- remove only Cue-owned media published into that designated test root;
- remove or archive the test instance's Cue state and generated exports;
- preserve imported/external files, all production roots, and all files outside
  the declared root; and
- take and verify a database backup before it permits any irreversible step.

No reset should infer ownership from a filename alone. Cue needs durable
provenance plus a root-bound ownership marker/manifest before it can safely
offer file deletion. Until then, cleanup remains an operator-managed filesystem
operation in a dedicated test folder.

## Implementation slices

1. **Setup status/read-only checklist:** derive and display current root,
   storage/worker health, import state, collection state, review count, and
   export state. No new writes beyond an optional dismissed-checklist flag.
2. **Guided first collection:** connect the current JSON preview, snapshot
   approval, Jobs, review, and export pages with resumable links and plain
   language. Preserve all existing APIs and approval gates.
3. **Library/workspace model:** only if multi-root use proves necessary, add
   explicit workspace records, per-workspace media roots, ownership and
   provenance rules, and migration/backup design.
4. **Test reset:** only after slice 3 gives Cue authoritative ownership data;
   implement preview, backup, typed confirmation, durable deletion job,
   cancellation boundary, audit events, and recovery report.

## Acceptance criteria

- A new user can reach a first approved source snapshot from the dashboard
  without consulting deployment or API documentation.
- Every step states whether it is read-only, preview-only, queued work, or an
  explicit publication/import approval.
- An existing-library user cannot mistake the workflow for permission to alter
  their source files.
- A test setup is visibly labelled with its exact physical root and cannot
  affect production files or state.
- A future reset has a complete preview, verified backup, narrow owned-file
  scope, typed confirmation, durable progress, cancellation, failure visibility,
  and audit trail.
- Expert users can still navigate directly to Library, Collections, Jobs,
  Review, and Exports.

## Related work

- [Getting started](getting-started.md) documents the current manual paths.
- [Library quality audit proposal](library-quality-audit.md) covers a separate
  read-only rehabilitation workflow.
- Channel identity/trust is a complementary acquisition improvement: a trusted
  official channel can be ranking evidence, but never a bypass of correct-song
  matching or explicit review rules.
