# Candidate policy and publisher authority

## Status

The initial collection-scoped policy is implemented. It records stable YouTube
channel IDs returned by yt-dlp and makes review/selection policy-aware. It is
an incremental foundation, not an assertion that Cue can determine universal
music rights ownership.

## Evidence layers

Cue keeps these questions distinct:

1. **Song identity:** whether the candidate title supports the requested
   artist/title. Wrong-song candidates are rejected.
2. **Format:** official music video, lyric video, live performance, remaster,
   audio, and other review-required formats.
3. **Publisher authority:** observed artist-channel name and owner-confirmed
   stable YouTube channel IDs.
4. **Collection policy:** the way a particular collection uses those signals.

An “Official” word in a title is evidence, not authority. It does not by itself
make a fan upload an automatic selection.

## Current collection controls

Each collection exposes **Candidate channel policy**. Enter one YouTube channel
ID per line (for example an artist channel, Vevo channel, label, or distributor
such as Rhino) and choose one rule:

- **Prefer these channels**: matching IDs receive a ranking boost and the
  reason is displayed.
- **Only these channels**: candidates outside the IDs remain visible as
  evidence but cannot be selected or downloaded for that collection.
- **Exclude these channels**: matching IDs cannot be selected or downloaded.

The policy is collection-scoped. Candidate metadata remains globally reusable,
but a live-performance collection can use different channel constraints from an
official-video collection.

Explicitly trusted channels can satisfy the strict automatic-selection
authority requirement only when the candidate is also a correct-song official
music video. Other formats remain review-only.

## Named channel trust and safe re-ranking

2026-08-15: Cue also has an owner-scoped **Channel trust and safe re-ranking**
workflow. From a candidate that is visible in one of the owner's collections,
the owner can classify its stable channel ID as an artist, VEVO, label, or
distributor. The decision and the observed channel name are audited; trust is
never inferred from a mutable display name alone.

Trust affects the effective candidate score and can supply the strict authority
evidence for a correct-song official music video. It does not change an
already-published asset or a person's selection. A separate durable
`reassess_collection_candidates` job re-evaluates stored candidates with the
new evidence, persists progress, and produces `auto_selected` recommendations.
That job queues zero downloads. Each recommendation has its own explicit
**Approve & queue recommendation** action.

## Ranking behavior

The default music-video policy ranks a correct-song official music video above
an artist-channel lyric video. It marks lyric and live formats as lower
priority rather than treating them as equivalent to a music video. This keeps
the strict default while leaving room for future format profiles.

Examples captured during the classic-rock validation run:

- `Van Halen — Jump`: correct-song identity prevents `Panama` from competing.
- `Bruce Springsteen — Born in the U.S.A.`: an unknown uploader's “Official
  Music Video” title claim is not enough for automatic selection.
- `Foreigner — I Want to Know What Love Is`: Rhino's official music video
  outranks Foreigner's lyric video; trusting Rhino's stable channel ID supplies
  auditable publisher authority.

## Deliberately next

“Only these channels” currently is a hard **selection/download** constraint.
Cue must still add dedicated per-channel discovery before it can promise that
every allowed channel was searched: filtering a generic search result set is
not sufficient. That work needs a channel URL/ID query strategy, query
provenance, combined pagination/deduplication, and clear reporting of each
channel searched.

Future work includes channel/network relationships, format profiles
(official-video, live-performance, broad), channel-specific discovery, and
editing/removing a trust relationship in the dashboard. All automatic trust
remains explicit, auditable, and overrideable.
