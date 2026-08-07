from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ProviderDocument:
    """Normalized preview document plus the immutable provider capture."""

    document: dict[str, Any]


def fetch_billboard_hot_100(configured_source: str, chart_date: date | None = None) -> ProviderDocument:
    """Fetch a user-configured billboard-hot-100 JSON endpoint and normalize it.

    Cue intentionally does not bundle or endorse a Billboard data source.  The
    operator must provide an exact raw GitHub JSON URL or a raw GitHub base URL
    for their personal copy of mhollingshead/billboard-hot-100-compatible data.
    """
    requested_url = billboard_source_url(configured_source, chart_date)
    request = Request(requested_url, headers={"Accept": "application/json", "User-Agent": "Cue/0.1"})
    try:
        with urlopen(request, timeout=20) as response:
            fetched_url = response.geturl()
            _validate_raw_github_url(fetched_url)
            raw_source = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Could not fetch Billboard source JSON: {exc}") from exc

    if not isinstance(raw_source, dict):
        raise ValueError("Billboard source JSON must be an object")
    rows = raw_source.get("data")
    if not isinstance(rows, list):
        raise ValueError("Billboard source JSON must contain a data array")

    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            items.append({"provider_row": row})
            continue
        item: dict[str, Any] = {
            "artists": [row["artist"]] if isinstance(row.get("artist"), str) else None,
            "title": row.get("song"),
            "provider_row": row,
        }
        if isinstance(row.get("this_week"), int) and not isinstance(row["this_week"], bool):
            item["rank"] = row["this_week"]
        items.append(item)

    return ProviderDocument(
        document={
            "source": "Billboard Hot 100 (user-configured GitHub source)",
            "source_url": fetched_url,
            "items": items,
            "provenance": {
                "adapter": "billboard_hot_100",
                "configured_url": configured_source,
                "fetched_url": fetched_url,
                "fetched_at": datetime.now(UTC).isoformat(),
                "chart_date": raw_source.get("date"),
                "raw_source_json": raw_source,
            },
        }
    )


def fetch_xmplaylist_recent(station: str = "altnation", window_hours: int = 24) -> ProviderDocument:
    """Capture a recent-play page from xmplaylist as an immutable preview."""
    station = station.strip().lower()
    if not station or not station.replace("-", "").isalnum():
        raise ValueError("xmplaylist station must contain only lowercase letters, digits, and hyphens")
    if not 1 <= window_hours <= 24 * 30:
        raise ValueError("xmplaylist window must be between 1 hour and 30 days")
    requested_url = f"https://xmplaylist.com/api/station/{station}"
    request = Request(requested_url, headers={"Accept": "application/json", "User-Agent": "Cue/0.1"})
    try:
        with urlopen(request, timeout=20) as response:
            fetched_url = response.geturl()
            if urlsplit(fetched_url).hostname != "xmplaylist.com":
                raise ValueError("xmplaylist redirected outside xmplaylist.com")
            raw_source = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Could not fetch xmplaylist source JSON: {exc}") from exc
    if not isinstance(raw_source, dict) or not isinstance(raw_source.get("results"), list):
        raise ValueError("xmplaylist source JSON must contain a results array")

    fetched_at = datetime.now(UTC)
    cutoff = fetched_at - timedelta(hours=window_hours)
    items: list[dict[str, Any]] = []
    for row in raw_source["results"]:
        if not isinstance(row, dict):
            items.append({"provider_row": row})
            continue
        timestamp = row.get("timestamp")
        if isinstance(timestamp, str):
            try:
                played_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if played_at.tzinfo is not None and played_at < cutoff:
                    continue
            except ValueError:
                pass
        track = row.get("track")
        if not isinstance(track, dict):
            items.append({"provider_row": row})
            continue
        items.append(
            {
                "artists": track.get("artists"),
                "title": track.get("title"),
                "source_id": track.get("id"),
                "played_at": timestamp,
                "provider_row": row,
            }
        )
    channel = raw_source.get("channel")
    channel_name = channel.get("name") if isinstance(channel, dict) else station
    return ProviderDocument(
        document={
            "source": f"xmplaylist recent plays: {channel_name}",
            "source_url": fetched_url,
            "items": items,
            "provenance": {
                "adapter": "xmplaylist_recent",
                "station": station,
                "window_hours": window_hours,
                "fetched_url": fetched_url,
                "fetched_at": fetched_at.isoformat(),
                "raw_source_json": raw_source,
            },
        }
    )


def billboard_source_url(configured_source: str, chart_date: date | None = None) -> str:
    configured_source = configured_source.strip()
    parsed = urlsplit(configured_source)
    _validate_raw_github_url(configured_source)
    if parsed.path.endswith(".json"):
        if chart_date is not None:
            raise ValueError("A chart date requires a GitHub raw base URL, not an exact JSON URL")
        return configured_source
    base = configured_source.rstrip("/")
    suffix = f"date/{chart_date.isoformat()}.json" if chart_date else "recent.json"
    return f"{base}/{suffix}"


def _validate_raw_github_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com" or not parsed.path.strip("/"):
        raise ValueError("Billboard source must be an HTTPS raw.githubusercontent.com URL or base URL")
    if parsed.query or parsed.fragment:
        raise ValueError("Billboard source URL must not include a query string or fragment")
