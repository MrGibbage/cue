from __future__ import annotations

import re
from dataclasses import dataclass

from cue.discovery import normalize_text

NEGATIVE = {"cover", "karaoke", "reaction", "remix", "live", "lyric", "visualizer", "audio", "remaster"}


@dataclass(frozen=True)
class ScoreResult:
    score: int
    classifications: list[str]
    reasons: list[str]


def score_candidate(artists: list[str], title: str, candidate_title: str, uploader: str | None) -> ScoreResult:
    observed = normalize_text(candidate_title)
    classifications = sorted(word for word in NEGATIVE if re.search(rf"\b{word}\b", observed))
    if not classifications and "official" in observed and ("music video" in observed or "official video" in observed):
        classifications.append("official_music_video")
    score = 0
    reasons: list[str] = []
    if normalize_text(title) in observed:
        score += 50
        reasons.append("title match")
    if all(normalize_text(artist) in observed for artist in artists):
        score += 30
        reasons.append("artist match")
    if "official" in observed:
        score += 20
        reasons.append("official title signal")
    if uploader and any(normalize_text(artist) in normalize_text(uploader) for artist in artists):
        score += 15
        reasons.append("uploader matches artist")
    if classifications:
        score -= 40
        reasons.append(f"review-required format: {', '.join(classifications)}")
    return ScoreResult(max(score, 0), classifications, reasons)
