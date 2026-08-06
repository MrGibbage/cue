from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from cue.discovery import canonical_key
from cue.models import CandidateAsset, Recording

SUPPORTED_CONTAINERS = {".mp4", ".mkv"}
_YEAR_SUFFIX = re.compile(r"\s*\[(\d{4})\]\s*$")
_DESCRIPTOR_SUFFIX = re.compile(r"\s*\(([^()]*)\)\s*$")


@dataclass(frozen=True)
class ParsedLibraryFile:
    artists: list[str] | None
    title: str | None
    descriptor: str | None
    year: int | None
    error: str | None

    @property
    def canonical_key(self) -> str | None:
        return canonical_key(self.artists, self.title) if self.artists and self.title else None


def parse_library_filename(filename: str) -> ParsedLibraryFile:
    """Conservatively parse ``Artist - Title (descriptor) [year].ext``."""
    stem = Path(filename).stem.strip()
    year: int | None = None
    descriptor: str | None = None
    year_match = _YEAR_SUFFIX.search(stem)
    if year_match:
        year = int(year_match.group(1))
        stem = stem[: year_match.start()].strip()
    descriptor_match = _DESCRIPTOR_SUFFIX.search(stem)
    if descriptor_match:
        descriptor = descriptor_match.group(1).strip() or None
        stem = stem[: descriptor_match.start()].strip()
    if " - " not in stem:
        return ParsedLibraryFile(None, None, descriptor, year, "Expected 'Artist - Title' filename format")
    artist_text, title = stem.split(" - ", 1)
    artist_parts = re.split(r"\s*(?:&|feat\.?|ft\.?)\s*", artist_text, flags=re.IGNORECASE)
    artists = [part.strip() for part in artist_parts if part.strip()]
    title = title.strip()
    if not artists or not title:
        return ParsedLibraryFile(None, None, descriptor, year, "Artist and title must both be present")
    return ParsedLibraryFile(artists, title, descriptor, year, None)


def scan_library(media_root: Path) -> list[tuple[Path, ParsedLibraryFile]]:
    """Return supported media files without following or exposing hidden paths."""
    root = media_root.resolve()
    if not root.is_dir():
        raise ValueError("Configured media root does not exist or is not a directory")
    results: list[tuple[Path, ParsedLibraryFile]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in SUPPORTED_CONTAINERS:
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        results.append((path, parse_library_filename(path.name)))
    return results


def safe_filename(recording: Recording, candidate: CandidateAsset, extension: str) -> str:
    artists = " & ".join(json.loads(recording.artists_json))
    return (
        f"{clean_component(artists)} - {clean_component(recording.title)} "
        f"[{clean_component(candidate.provider_id)}]{extension.lower()}"
    )


def clean_component(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(". ")


def publish_atomically(source: Path, media_root: Path, filename: str) -> Path:
    media_root.mkdir(parents=True, exist_ok=True)
    destination = media_root / filename
    if destination.exists():
        raise FileExistsError(f"Refusing to replace existing library file: {destination.name}")
    temporary = media_root / f".{filename}.partial"
    try:
        if source.resolve().parent == media_root.resolve():
            source.replace(temporary)
        else:
            shutil.copy2(source, temporary)
            source.unlink()
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
