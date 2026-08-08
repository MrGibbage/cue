from fastapi.testclient import TestClient

from cue.api import create_app
from cue.config import Settings


def test_health_and_readiness(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=tmp_path,
        session_secret="test-session-secret-that-is-long-enough",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/readyz").json() == {"status": "ready"}
        schema = client.get("/api/v1/song-list-schema")
        assert schema.status_code == 200
        assert schema.json()["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema.json()["oneOf"][1]["properties"]["items"]["items"]["required"] == ["artists", "title"]


def test_dashboard_shell(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=tmp_path,
        session_secret="test-session-secret-that-is-long-enough",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Sign in" in response.text
