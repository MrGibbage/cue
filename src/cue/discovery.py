from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

MAX_JSON_DOCUMENT_BYTES = 2 * 1024 * 1024
# Kept as a public alias for callers that describe the limit in upload terms.
MAX_JSON_UPLOAD_BYTES = MAX_JSON_DOCUMENT_BYTES
MAX_SOURCE_NAME_CHARS = 255
MAX_SOURCE_URL_CHARS = 2048
MAX_ARTISTS_PER_ITEM = 16
MAX_ARTIST_CHARS = 255
MAX_TITLE_CHARS = 512
MIN_SQLITE_INTEGER = -(2**63)
MAX_SQLITE_INTEGER = 2**63 - 1


def song_list_json_schema() -> dict[str, Any]:
    """Return the portable schema for a valid Cue song-list document."""
    item = {
        "type": "object",
        "required": ["artists", "title"],
        "properties": {
            "artists": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_ARTISTS_PER_ITEM,
                "items": {"type": "string", "minLength": 1, "maxLength": MAX_ARTIST_CHARS},
            },
            "title": {"type": "string", "minLength": 1, "maxLength": MAX_TITLE_CHARS},
            "rank": {"type": "integer", "minimum": MIN_SQLITE_INTEGER, "maximum": MAX_SQLITE_INTEGER},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Cue song list",
        "description": "A list of desired recordings for Cue preview and explicit approval.",
        "oneOf": [
            {"type": "array", "items": item},
            {
                "type": "object",
                "required": ["items"],
                "properties": {
                    "source": {"type": "string", "maxLength": MAX_SOURCE_NAME_CHARS},
                    "source_url": {"type": "string", "maxLength": MAX_SOURCE_URL_CHARS},
                    "items": {"type": "array", "items": item},
                },
            },
        ],
    }


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).casefold()
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())


def canonical_key(artists: list[str], title: str) -> str:
    return f"{' | '.join(normalize_text(artist) for artist in artists)} :: {normalize_text(title)}"


def parse_json_document_bytes(data: bytes) -> dict[str, Any] | list[Any]:
    """Decode a bounded UTF-8 song-list JSON document."""
    if len(data) > MAX_JSON_DOCUMENT_BYTES:
        raise ValueError(f"JSON document exceeds the {MAX_JSON_DOCUMENT_BYTES // (1024 * 1024)} MiB limit")
    document = json.loads(data.decode("utf-8"))
    if not isinstance(document, (dict, list)):
        raise ValueError("JSON document must be an array or an object containing an items array")
    return document


def parse_uploaded_document(data: bytes) -> dict[str, Any] | list[Any]:
    """Decode a bounded UTF-8 JSON list document uploaded through the UI/API."""
    return parse_json_document_bytes(data)


def validate_document_size(document: Any) -> None:
    """Apply the intake size limit to parsed API documents and provider output."""
    size = len(json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > MAX_JSON_DOCUMENT_BYTES:
        raise ValueError(f"JSON document exceeds the {MAX_JSON_DOCUMENT_BYTES // (1024 * 1024)} MiB limit")


@dataclass(frozen=True)
class PreviewRow:
    position: int
    supplied_rank: int | None
    artists: list[str] | None
    title: str | None
    canonical_key: str | None
    status: str
    error: str | None
    raw: Any


@dataclass(frozen=True)
class PreviewDocument:
    source_name: str | None
    source_url: str | None
    rows: list[PreviewRow]


def apply_discovery_recipe(document: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
    """Apply explicit provider discovery rules without changing raw provenance."""
    rules = recipe.get("discovery", {})
    if not isinstance(rules, dict) or not isinstance(document.get("items"), list):
        return document

    def terms(name: str) -> list[str]:
        value = rules.get(name, [])
        if not isinstance(value, list):
            return []
        return [normalize_text(item) for item in value if isinstance(item, str) and item.strip()]

    include, exclude, title_contains = terms("include_artists"), terms("exclude_artists"), terms("title_contains")
    filtered: list[Any] = []
    for item in document["items"]:
        if not isinstance(item, dict):
            filtered.append(item)
            continue
        artists = item.get("artists")
        artist_text = (
            " ".join(normalize_text(artist) for artist in artists if isinstance(artist, str))
            if isinstance(artists, list)
            else ""
        )
        title_text = normalize_text(item["title"]) if isinstance(item.get("title"), str) else ""
        if include and not any(term in artist_text for term in include):
            continue
        if exclude and any(term in artist_text for term in exclude):
            continue
        if title_contains and not all(term in title_text for term in title_contains):
            continue
        filtered.append(item)
    if rules.get("order") == "rank":
        filtered.sort(key=lambda item: item.get("rank", 2**31) if isinstance(item, dict) else 2**31)
    limit = rules.get("limit")
    if isinstance(limit, int) and not isinstance(limit, bool) and limit >= 0:
        filtered = filtered[:limit]
    result = dict(document)
    result["items"] = filtered
    provenance = result.get("provenance")
    if isinstance(provenance, dict):
        result["provenance"] = {**provenance, "recipe_discovery_rules": rules, "rows_after_recipe": len(filtered)}
    return result


def parse_document(document: Any) -> PreviewDocument:
    validate_document_size(document)
    source_name: str | None = None
    source_url: str | None = None
    if isinstance(document, list):
        items = document
    elif isinstance(document, dict):
        items = document.get("items")
        source_name = document.get("source")
        source_url = document.get("source_url")
        if source_name is not None and (
            not isinstance(source_name, str) or len(source_name.strip()) > MAX_SOURCE_NAME_CHARS
        ):
            raise ValueError(f"source must be a string of at most {MAX_SOURCE_NAME_CHARS} characters when supplied")
        if source_url is not None and (
            not isinstance(source_url, str) or len(source_url.strip()) > MAX_SOURCE_URL_CHARS
        ):
            raise ValueError(f"source_url must be a string of at most {MAX_SOURCE_URL_CHARS} characters when supplied")
        source_name = source_name.strip() or None if source_name is not None else None
        source_url = source_url.strip() or None if source_url is not None else None
    else:
        raise ValueError("JSON document must be an array or an object containing an items array")
    if not isinstance(items, list):
        raise ValueError("JSON document items must be an array")

    seen: set[str] = set()
    rows: list[PreviewRow] = []
    for position, raw in enumerate(items):
        artists: list[str] | None = None
        title: str | None = None
        supplied_rank: int | None = None
        error: str | None = None
        if not isinstance(raw, dict):
            error = "Entry must be an object"
        else:
            raw_artists = raw.get("artists")
            raw_title = raw.get("title")
            raw_rank = raw.get("rank")
            if not isinstance(raw_artists, list) or not raw_artists:
                error = "artists must be a non-empty array"
            elif len(raw_artists) > MAX_ARTISTS_PER_ITEM:
                error = f"artists may contain at most {MAX_ARTISTS_PER_ITEM} entries"
            elif not all(isinstance(artist, str) and artist.strip() for artist in raw_artists):
                error = "artists must contain only non-empty strings"
            elif any(len(artist.strip()) > MAX_ARTIST_CHARS for artist in raw_artists):
                error = f"each artist must be at most {MAX_ARTIST_CHARS} characters"
            elif not isinstance(raw_title, str) or not raw_title.strip():
                error = "title must be a non-empty string"
            elif len(raw_title.strip()) > MAX_TITLE_CHARS:
                error = f"title must be at most {MAX_TITLE_CHARS} characters"
            elif raw_rank is not None and (
                not isinstance(raw_rank, int)
                or isinstance(raw_rank, bool)
                or not MIN_SQLITE_INTEGER <= raw_rank <= MAX_SQLITE_INTEGER
            ):
                error = "rank must be a SQLite-compatible integer when supplied"
            else:
                artists = [artist.strip() for artist in raw_artists]
                title = raw_title.strip()
                supplied_rank = raw_rank
        key = canonical_key(artists, title) if artists is not None and title is not None else None
        row_status = "rejected" if error else "accepted"
        if key and key in seen:
            row_status = "duplicate"
            error = "Duplicate desired recording; the first occurrence is retained"
        elif key:
            seen.add(key)
        rows.append(PreviewRow(position, supplied_rank, artists, title, key, row_status, error, raw))
    return PreviewDocument(source_name, source_url, rows)
