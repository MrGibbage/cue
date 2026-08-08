# Getting started with Cue

This guide walks through building a first Cue library safely. It covers both
an existing folder of music videos and a new collection that Cue acquires.
Every source run is previewed first; Cue never queues downloads or imports
files until you explicitly approve it.

## Before you begin

1. Deploy Cue with the media directory mounted as `CUE_MEDIA_ROOT` (the
   Compose deployment mounts it at `/media`). The API container has read-only
   media access; only the worker can publish media.
2. Set a long, unique `CUE_SESSION_SECRET` and bootstrap administrator values
   for the first start, as described in the [README](../README.md#milestone-1-setup).
   Remove the bootstrap password from the environment file once the account
   exists.
3. Open Cue in a browser and sign in. On the supplied deployment this is
   `https://cue.pelorus.org`.

## Option A: bring an existing library under Cue

Use this first when you already have files in the mounted media directory.
The scan is read-only and does not rename, move, or delete anything.

1. Open **Library** in the navigation.
2. Select **Scan existing library**.
3. Inspect the preview:
   - **accepted** means Cue parsed a conservative `Artist - Title` identity;
   - **review** means the filename is ambiguous or conflicts with another
     proposed recording;
   - **already imported** is already managed by Cue and will be skipped.
4. Select **Approve accepted files** only after checking the results.
5. Return to **Library** to confirm the imported assets. Future collections
   reuse these assets when their recording identity matches, rather than
   downloading them again.

Rows needing review remain untouched. Correct the source filename or keep the
asset outside Cue until you can make an explicit decision; running another
preview is safe.

## Option B: build a new collection

1. From **Dashboard**, create a collection and give it a descriptive name.
2. Open the new collection. Choose one source method:
   - Paste a JSON list. The minimal format is:

     ```json
     [
       {"artists": ["The Clash"], "title": "London Calling", "rank": 1},
       {"artists": ["Rush"], "title": "Tom Sawyer", "rank": 2}
     ]
     ```

     `rank` is optional; without it, array order becomes collection order.
     JSON can also be an object with `source`, `source_url`, and `items` to
     preserve your own source metadata. See the complete
     [song-list JSON reference](song-list-json.md).
   - Use **Billboard Hot 100** only with a URL or base URL you configure for
     your personal GitHub copy of compatible JSON data. Cue does not bundle or
     license a Billboard source. Entering a base fetches `recent.json`; adding
     a chart date fetches `date/YYYY-MM-DD.json`.
   - Use **Alt Nation recent plays** to capture xmplaylist’s Alt Nation history
     for a chosen lookback window.
3. Review the resulting snapshot. It lists accepted, rejected, and duplicate
   rows. Select the snapshot number to see the full immutable source capture,
   fetched URL(s), timestamps, adapter, and raw JSON.
4. Select **Approve & queue** only when the desired recordings are correct.
   Approval creates the durable matching job; preview alone does not start
   acquisition.
5. Open **Jobs** to monitor the run. Cue automatically downloads only
   high-confidence official-video matches. It sends uncertain items to the
   collection’s review choices instead.
6. In the collection’s **Current resolved list**, inspect candidates marked
   **review** and use **Select** only for the version you want. Cue then queues
   that explicit download.

Cue deduplicates published recordings globally. If a collection asks for a
recording you already imported or published, Cue links the existing asset and
does not download it again.

## Export the completed collection

1. From the collection, choose **Preview M3U8 export**.
2. Check the resolved order and missing-item count.
3. Select **Approve and publish**.
4. Download the `.m3u8` and its missing-item report from the export page.

The playlist contains only published assets in collection order. Missing,
unresolved, or deliberately skipped recordings remain in the JSON report so
they are visible rather than silently disappearing.

## Operations and recovery

- **Diagnostics** shows the latest backup, queued/failed jobs, review count,
  and recent provider fetch errors. An upstream rate limit is recorded there
  with its provider error text.
- A failed job is terminal after its configured attempts. Open **Jobs** and
  choose **Retry** only after correcting the cause.
- The worker creates a verified daily SQLite backup. See the
  [README backup and restore instructions](../README.md#backups-and-restore)
  before attempting a restore; restores always require a new destination.

For a full release-validation run, see the [MVP acceptance exercise](mvp-acceptance.md).
