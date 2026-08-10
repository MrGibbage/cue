from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderCandidate:
    provider_id: str
    url: str
    title: str
    uploader: str | None
    duration_seconds: int | None


def _cookie_arguments(cookies_file: Path | None) -> list[str]:
    if cookies_file and cookies_file.is_file() and cookies_file.stat().st_size:
        return ["--cookies", str(cookies_file)]
    return []


def search_youtube(
    artists: list[str], title: str, *, limit: int = 5, cookies_file: Path | None = None
) -> list[ProviderCandidate]:
    """Return yt-dlp search metadata only; this function never downloads media."""
    query = f"{' '.join(artists)} {title} official music video"
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--no-playlist", *_cookie_arguments(cookies_file), f"ytsearch{limit}:{query}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp search failed")
    candidates: list[ProviderCandidate] = []
    for line in result.stdout.splitlines():
        data = json.loads(line)
        identifier = data.get("id")
        webpage_url = data.get("webpage_url")
        candidate_title = data.get("title")
        if not all(isinstance(value, str) and value for value in (identifier, webpage_url, candidate_title)):
            continue
        duration = data.get("duration")
        candidates.append(
            ProviderCandidate(
                provider_id=identifier,
                url=webpage_url,
                title=candidate_title,
                uploader=data.get("uploader") if isinstance(data.get("uploader"), str) else None,
                duration_seconds=int(duration) if isinstance(duration, (int, float)) else None,
            )
        )
    return candidates


def download_youtube(url: str, destination_template: Path, *, cookies_file: Path | None = None) -> Path:
    """Download one approved candidate into private staging."""
    result = subprocess.run(
        [
            "yt-dlp",
            "--no-playlist",
            "--no-progress",
            *_cookie_arguments(cookies_file),
            "--format",
            "bv*+ba/b",
            "--merge-output-format",
            "mp4",
            "--output",
            str(destination_template),
            url,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "yt-dlp download failed")
    files = [
        path
        for path in destination_template.parent.glob(f"{destination_template.stem}.*")
        if path.suffix.lower() in {".mp4", ".mkv"}
    ]
    if len(files) != 1:
        raise RuntimeError("yt-dlp did not produce exactly one supported media file")
    return files[0]


def validate_video(path: Path) -> None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "ffprobe validation failed")
    if not json.loads(result.stdout).get("streams"):
        raise RuntimeError("download has no video stream")
