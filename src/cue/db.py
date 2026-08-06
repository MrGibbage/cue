from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from cue.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL"))
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(text("PRAGMA busy_timeout=5000"))
    return engine


def run_migrations(settings: Settings) -> None:
    config = Config(str(Path.cwd() / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")


def database_ready(engine: Engine) -> bool:
    with engine.connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1
