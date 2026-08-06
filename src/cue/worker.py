from __future__ import annotations

import logging
import signal
from threading import Event

from cue.config import get_settings
from cue.db import create_db_engine, run_migrations
from cue.logging import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    run_migrations(settings)
    engine = create_db_engine(settings)
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    logger.info("Cue worker started; no job handlers are enabled in Milestone 0")
    stop.wait()
    engine.dispose()
    logger.info("Cue worker stopped")
