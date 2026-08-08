from fastapi.testclient import TestClient

from cue.api import create_app
from cue.config import Settings
from cue.discovery_providers import ProviderDocument


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
        assert "Instructions to the LLM: Generate a song list" in page.text
        assert "Copy instructions" in page.text
        preview = client.post(
            "/collections/1/json-previews",
            data={
                "csrf_token": _csrf(client),
                "document": (
                    '{"source":"External list","source_url":"javascript:alert(1)",'
                    '"items":[{"artists":["Rush"],"title":"Tom Sawyer","rank":2}]}'
                ),
            },
            follow_redirects=False,
        )
        assert preview.status_code == 303
        collection_page = client.get("/collections/1").text
        assert "Created preview #1: 1 accepted, 0 duplicates, 0 rejected." in collection_page
        assert "1 accepted · 0 duplicates · 0 rejected" in collection_page
        assert "javascript:alert(1)" in collection_page
        assert 'href="javascript:' not in collection_page
        snapshot_page = client.get("/snapshots/1").text
        assert "Source #" in snapshot_page
        assert ">2</td>" in snapshot_page
        upload = client.post(
            "/collections/1/json-upload-previews",
            data={"csrf_token": _csrf(client)},
            files={"file": ("party.json", b'[{"artists":["Prince"],"title":"1999"}]', "application/json")},
            follow_redirects=True,
        )
        assert "Created preview #2: 1 accepted, 0 duplicates, 0 rejected. Uploaded from party.json." in upload.text
        invalid_preview = client.post(
            "/collections/1/json-previews",
            data={"csrf_token": _csrf(client), "document": '[{"artists":[],"title":"Missing artist"}]'},
            follow_redirects=True,
        )
        assert "Fix rejected rows or create a new list before approval." in invalid_preview.text
        assert 'action="/snapshots/3/approve"' not in invalid_preview.text
        saved = client.post(
            "/settings",
            data={"csrf_token": _csrf(client), "default_download_batch_size": "7"},
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert 'value="7"' in client.get("/settings").text


def test_dashboard_creates_user_configured_billboard_preview(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "cue.web.fetch_billboard_hot_100",
        lambda configured_source, chart_date: ProviderDocument(
            {
                "source": "Billboard Hot 100 (user-configured GitHub source)",
                "source_url": "https://raw.githubusercontent.com/example/charts/main/recent.json",
                "items": [{"artists": ["Sabrina Carpenter"], "title": "Espresso", "rank": 1}],
                "provenance": {
                    "adapter": "billboard_hot_100",
                    "configured_url": configured_source,
                    "fetched_url": "https://raw.githubusercontent.com/example/charts/main/recent.json",
                    "fetched_at": "2026-08-07T00:00:00+00:00",
                    "raw_source_json": {"data": []},
                },
            }
        ),
    )
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=tmp_path,
        session_secret="test-session-secret-that-is-long-enough",
        bootstrap_admin_username="owner",
        bootstrap_admin_password="correct-horse-battery-staple",
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        client.post("/login", data={"username": "owner", "password": "correct-horse-battery-staple"})
        client.post("/collections", data={"name": "Chart", "csrf_token": _csrf(client)})
        preview = client.post(
            "/collections/1/billboard-hot-100-previews",
            data={
                "csrf_token": _csrf(client),
                "configured_source": "https://raw.githubusercontent.com/example/charts/main",
            },
            follow_redirects=True,
        )
    assert "Created Billboard preview #1" in preview.text
    assert "user-configured GitHub source" in preview.text
    assert "configured: https://raw.githubusercontent.com/example/charts/main" in preview.text
    snapshot = client.get("/snapshots/1")
    assert "Immutable provenance and raw source capture" in snapshot.text
    assert '"raw_source_json"' in snapshot.text


def _csrf(client: TestClient) -> str:
    # The signed session is opaque; obtain the token from a rendered hidden field.
    import re

    page = client.get("/").text
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
