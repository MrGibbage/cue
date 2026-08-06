from fastapi.testclient import TestClient

from cue.api import create_app
from cue.config import Settings


def test_dashboard_login_collection_json_preview_and_settings(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=tmp_path,
        session_secret="test-session-secret-that-is-long-enough",
        bootstrap_admin_username="owner",
        bootstrap_admin_password="correct-horse-battery-staple",
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        assert "Sign in" in client.get("/").text
        login = client.post(
            "/login",
            data={"username": "owner", "password": "correct-horse-battery-staple"},
            follow_redirects=True,
        )
        assert "Good to see you, owner" in login.text
        collection = client.post(
            "/collections",
            data={"name": "Dashboard Rock", "csrf_token": _csrf(client)},
            follow_redirects=False,
        )
        assert collection.status_code == 303
        page = client.get(collection.headers["location"])
        assert "Dashboard Rock" in page.text
        preview = client.post(
            "/collections/1/json-previews",
            data={"csrf_token": _csrf(client), "document": '[{"artists":["Rush"],"title":"Tom Sawyer"}]'},
            follow_redirects=False,
        )
        assert preview.status_code == 303
        assert "Created preview #1" in client.get("/collections/1").text
        saved = client.post(
            "/settings",
            data={"csrf_token": _csrf(client), "default_download_batch_size": "7"},
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert 'value="7"' in client.get("/settings").text


def _csrf(client: TestClient) -> str:
    # The signed session is opaque; obtain the token from a rendered hidden field.
    import re

    page = client.get("/").text
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
