from cue.config import Settings
from cue.notifications import notify


def test_notification_is_noop_without_configuration(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=tmp_path,
        session_secret="test-session-secret-that-is-long-enough",
    )
    notify(settings, "title", "body")
