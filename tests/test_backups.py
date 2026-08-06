from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from cue.backups import create_daily_backup, restore_backup
from cue.config import Settings
from cue.db import create_db_engine


def test_daily_online_backup_retention_and_non_overwriting_restore(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=tmp_path,
        backup_root=tmp_path / "backups",
        backup_retention_days=2,
        session_secret="test-session-secret-that-is-long-enough",
    )
    engine = create_db_engine(settings)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sample (value TEXT)"))
        connection.execute(text("INSERT INTO sample VALUES ('preserved')"))
    now = datetime(2026, 8, 6, tzinfo=UTC)
    backup = create_daily_backup(settings, now)
    create_daily_backup(settings, now - timedelta(days=3))
    create_daily_backup(settings, now)
    assert backup.exists()
    assert len(list(settings.backup_root.glob("*.sqlite3"))) == 1
    restored = tmp_path / "restored.sqlite3"
    restore_backup(backup, restored)
    import sqlite3

    with sqlite3.connect(restored) as database:
        assert database.execute("SELECT value FROM sample").fetchone() == ("preserved",)
    with pytest.raises(ValueError, match="already exists"):
        restore_backup(backup, restored)
    engine.dispose()
