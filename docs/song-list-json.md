# Cue song-list JSON reference

Cue is list-first: bring a set of songs from any source, preview it, and only
then decide whether to queue matching and acquisition. Paste JSON into a
collection, upload a UTF-8 `.json` file, or send the same shape to the API.
Every intake path accepts documents up to 2 MiB.

## Recommended document

```json
{
  "source": "Space-themed party playlist",
  "source_url": "https://example.com/my-list",
  "items": [
    {
      "artists": ["David Bowie"],
      "title": "Space Oddity",
      "rank": 1,
      "year": 1969,
      "notes": "Opening song"
    },
    {
      "artists": ["Elton John"],
      "title": "Rocket Man",
      "rank": 2
    }
  ]
}
```

An array is also valid when no document-level source metadata is needed:

```json
[
  {"artists": ["The B-52's"], "title": "Planet Claire"},
  {"artists": ["The Police"], "title": "Walking on the Moon"}
]
```

## Required item fields

- `artists`: a non-empty array of non-empty strings. Keep featured performers
  as separate entries when useful, such as `["Artist", "Featured artist"]`.
- `title`: a non-empty string.

## Optional fields

- `rank`: integer ordering. Cue orders ranked items first by ascending rank;
  unranked items retain source order after them.
- `source`, `source_url`: document-level provenance.
- `notes`, `year`, `album`, `source_id`, and other source-specific fields:
  preserved as raw row provenance even when Cue does not use them for matching.

## Preview behavior

- Valid entries are accepted even if other entries are invalid.
- Duplicate desired recordings in one list are reported; the first occurrence
  is retained.
- Cue retains raw input and preview rows as an immutable source snapshot.
- A preview does not create matching or download jobs. Use **Approve & queue**
  as a distinct action after reviewing it.

## Prompting an AI

In a collection page, expand **Ask an AI to make a Cue song list** and use
**Copy instructions**. It copies an instruction and schema that asks the model
to return JSON only. Review generated JSON in Cue just as you would any other
source—an AI-generated list is still only a proposed list, never an automatic
acquisition instruction.
