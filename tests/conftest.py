import pytest
from sqlalchemy.orm import Session

from cue.config import Settings
from cue.db import create_db_engine, run_migrations


@pytest.fixture
def session(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=tmp_path,
        session_secret="test-session-secret-that-is-long-enough",
    )
    run_migrations(settings)
    engine = create_db_engine(settings)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()
