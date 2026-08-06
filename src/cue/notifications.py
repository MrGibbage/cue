from __future__ import annotations

import json
import logging
from urllib.request import Request, urlopen

from cue.config import Settings

logger = logging.getLogger(__name__)


def notify(settings: Settings, title: str, body: str, notification_type: str = "info") -> None:
    """Best-effort Apprise notification; delivery failures never escape."""
    if settings.apprise_url is None:
        return
    payload = json.dumps({"title": title, "body": body, "type": notification_type}).encode()
    request = Request(str(settings.apprise_url), data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            response.read()
    except Exception:
        logger.exception("Apprise notification delivery failed")
