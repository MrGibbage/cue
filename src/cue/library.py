from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from cue.models import CandidateAsset, Recording


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
