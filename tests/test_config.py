import pytest
from pydantic import ValidationError

from cue.config import Settings


def test_staging_must_be_under_media_root(tmp_path):
    with pytest.raises(ValidationError, match="CUE_STAGING_ROOT"):
        Settings(
            database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
            media_root=tmp_path / "media",
            staging_root=tmp_path / "outside",
            session_secret="test-session-secret-that-is-long-enough",
        )
