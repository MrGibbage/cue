from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cue.config import Settings


def create_daily_backup(settings: Settings, now: datetime | None = None) -> Path:
    """Create one verified SQLite online backup per UTC day and prune old backups."""
    timestamp = now or datetime.now(UTC)
    settings.backup_root.mkdir(parents=True, exist_ok=True)
    destination = settings.backup_root / f"cue-{timestamp:%Y-%m-%d}.sqlite3"
    if not destination.exists():
        _sqlite_backup(settings.database_path, destination)
    cutoff = (timestamp - timedelta(days=settings.backup_retention_days)).date()
    for candidate in settings.backup_root.glob("cue-????-??-??.sqlite3"):
        try:
            if datetime.strptime(candidate.stem.removeprefix("cue-"), "%Y-%m-%d").date() < cutoff:
                candidate.unlink()
        except ValueError:
            continue
    return destination


def restore_backup(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise ValueError(f"Backup does not exist: {source}")
    if destination.exists():
        raise ValueError(f"Restore destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _sqlite_backup(source, destination)


def _sqlite_backup(source: Path, destination: Path) -> None:
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as destination_db:
        source_db.backup(destination_db)
        result = destination_db.execute("PRAGMA integrity_check").fetchone()
    if result != ("ok",):
        destination.unlink(missing_ok=True)
        raise RuntimeError("SQLite backup integrity check failed")
