# Title identity clarification proposal

## Status

**Proposed; no implementation yet.** This is a future intake and candidate
review capability. It does not alter existing snapshots, recordings, searches,
or approval rules.

## Problem

Cue accepts a structured song list from a person, spreadsheet, provider, or
LLM. The `title` field is intended to identify a released recording, but a
source can place arbitrary prose in it:

```json
{"artists": ["Lynyrd Skynyrd"], "title": "Free Bird (Live Revival Era Popularity)"}
```

Cue cannot safely know whether that parenthetical is stray commentary, a
source's editorial annotation, or a genuine request for a particular version.
It also must not treat parentheses as inherently suspicious: titles such as
The Rolling Stones' `(I Can't Get No) Satisfaction` are legitimate recording
titles.

## Product decision

Do not silently rewrite the submitted artist/title pair. Preserve the raw row
and immutable source snapshot exactly as supplied. Instead, use search evidence
to identify an unsupported or ambiguous requested identity and ask the owner a
specific question before it is treated as an ordinary acquisition decision.

The goal is not to prove a title is invalid. The goal is to distinguish:

- a literal artist/title pair supported by credible provider results;
- an intentional version constraint, such as live, remix, or acoustic; and
- an artist/title pair for which the source text appears to contain unrelated
  commentary or otherwise cannot be supported.

## Proposed evidence-driven flow

1. **Preserve literal source input.** Store the raw JSON row and retain its
   submitted artist/title untouched for provenance and later correction.
2. **Derive search variants without changing the record.** Search the literal
   title first. Where a qualifier can be separated without damaging balanced
   title punctuation, also search a conservative base-title variant. Record
   each query and why it was derived.
3. **Compare the evidence.** A high-confidence result for the literal title
   supports normal candidate ranking. Strong results for the base title but no
   support for the literal title create a clarification, not an automatic
   rewrite. No credible result for either makes the item unresolved.
4. **Ask a focused question.** For example:

   > No credible video matched `Lynyrd Skynyrd — Free Bird (Live Revival Era
   > Popularity)`. We found strong candidates for `Lynyrd Skynyrd — Free Bird`.
   > Did you mean that recording?

   The owner can choose:

   - **Use the base recording** and retain the original qualifier as source
     notes/provenance;
   - **Keep the qualifier as a version requirement**, for example requiring a
     live performance or a remaster;
   - **Correct the artist/title**; or
   - **Leave unresolved** for later review.
5. **Create a revised snapshot/version.** An accepted correction produces a
   new source snapshot/collection version. The original snapshot remains
   immutable and auditable. No candidate is downloaded merely by generating
   the clarification.

## Qualifier handling principles

- Parentheses, brackets, punctuation, and years are evidence, not a command to
  strip text. The title parser must preserve legitimate titles.
- Recognizable terms such as `live`, `remix`, `acoustic`, `remaster`, `radio
  edit`, and `demo` can inform the wording of the question, but are never
  silently converted into policy.
- Unknown multi-word prose is not assumed to be a title or a note. It is shown
  to the owner when search evidence disagrees.
- The submitted literal title, derived query variants, candidate evidence,
  owner decision, and resulting revised snapshot must all be visible in audit
  history.

## UI behavior

The normal candidate page should distinguish three things that are currently
easy to conflate:

- **Requested recording:** the literal artist/title from the approved source;
- **Search interpretation:** literal or relaxed/base-title query, with its
  rationale; and
- **Candidate suitability:** correct-song identity, publisher authenticity,
  format, and collection policy fit.

When no credible literal match exists, show the clarification card before the
ordinary candidate ordering. Zero-score/rejected search results remain stored
as audit evidence, but are collapsed by default instead of appearing as
plausible choices.

## LLM and JSON guidance

Cue's copyable list-generation instruction should request only the released
recording title in `title`. Context such as popularity period, rationale,
preferred version, or uncertainty belongs in `notes`. This is a quality aid,
not a trust boundary: Cue must still validate arbitrary JSON from any source.

## Acceptance criteria

- Legitimate parenthetical titles remain searchable and are never automatically
  truncated.
- Cue does not claim to know whether ambiguous source prose is a mistake.
- A literal identity with no credible provider support produces a clear,
  actionable owner question when a conservative alternative has evidence.
- A clarification cannot mutate an approved immutable snapshot or queue a
  download; an explicit owner choice creates a revised source version and
  follows normal approval.
- All query variants, evidence, decisions, and revisions are auditable.
- Rejected/zero-score provider results are available for diagnostics without
  overwhelming the default review experience.
