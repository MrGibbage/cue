from __future__ import annotations

import re
from dataclasses import dataclass

from cue.discovery import normalize_text

NEGATIVE = {"cover", "karaoke", "reaction", "remix", "live", "lyric", "visualizer", "audio", "remaster"}
_OFFICIAL_VIDEO = re.compile(r"\bofficial (?:music )?video\b")


@dataclass(frozen=True)
class ScoreResult:
    score: int
    classifications: list[str]
    reasons: list[str]


def score_candidate(artists: list[str], title: str, candidate_title: str, uploader: str | None) -> ScoreResult:
    observed = normalize_text(candidate_title)
    wanted_title = normalize_text(title)
    title_match = bool(re.search(rf"\b{re.escape(wanted_title)}\b", observed))
    classifications = sorted(word for word in NEGATIVE if re.search(rf"\b{word}\b", observed))
    if not title_match:
        classifications.append("wrong_song")
    if title_match and not classifications and _OFFICIAL_VIDEO.search(observed):
        classifications.append("official_music_video")
    score = 0
    reasons: list[str] = []
    if title_match:
        score += 50
        reasons.append("exact title match")
    if all(normalize_text(artist) in observed for artist in artists):
        score += 30
        reasons.append("artist match")
    if _OFFICIAL_VIDEO.search(observed):
        score += 15
        reasons.append("official-video title signal")
    normalized_uploader = normalize_text(uploader or "")
    normalized_artists = [normalize_text(artist) for artist in artists]
    if normalized_uploader and any(normalized_uploader == artist for artist in normalized_artists):
        score += 35
        reasons.append("uploader exactly matches artist")
    elif normalized_uploader and any(artist in normalized_uploader for artist in normalized_artists):
        score += 10
        reasons.append("uploader includes artist")
    negative_formats = [item for item in classifications if item not in {"official_music_video", "wrong_song"}]
    if negative_formats:
        score -= 50
        reasons.append(f"review-required format: {', '.join(negative_formats)}")
    if "wrong_song" in classifications:
        score -= 100
        reasons.append("candidate title does not contain the requested song title")
    return ScoreResult(max(min(score, 100), 0), sorted(classifications), reasons)
