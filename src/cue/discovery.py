from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).casefold()
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())


def canonical_key(artists: list[str], title: str) -> str:
    return f"{' | '.join(normalize_text(artist) for artist in artists)} :: {normalize_text(title)}"


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


def parse_document(document: Any) -> PreviewDocument:
    source_name: str | None = None
    source_url: str | None = None
    if isinstance(document, list):
        items = document
    elif isinstance(document, dict):
        items = document.get("items")
        source_name = document.get("source") if isinstance(document.get("source"), str) else None
        source_url = document.get("source_url") if isinstance(document.get("source_url"), str) else None
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
            elif not all(isinstance(artist, str) and artist.strip() for artist in raw_artists):
                error = "artists must contain only non-empty strings"
            elif not isinstance(raw_title, str) or not raw_title.strip():
                error = "title must be a non-empty string"
            elif raw_rank is not None and (not isinstance(raw_rank, int) or isinstance(raw_rank, bool)):
                error = "rank must be an integer when supplied"
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
