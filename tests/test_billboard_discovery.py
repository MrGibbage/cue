import json
from contextlib import contextmanager

from fastapi.testclient import TestClient

from cue.api import create_app
from cue.config import Settings
from cue.discovery_providers import billboard_source_url


@contextmanager
def _source_response(payload, url):
    class Response:
        def read(self):
            return json.dumps(payload).encode()

        def geturl(self):
            return url

    yield Response()


def test_billboard_preview_preserves_configured_and_fetched_source(monkeypatch, tmp_path):
    configured = "https://raw.githubusercontent.com/example/charts/main"
    fetched = "https://raw.githubusercontent.com/example/charts/main/date/2026-08-01.json"
    payload = {
        "date": "2026-08-01",
        "data": [
            {"song": "Espresso", "artist": "Sabrina Carpenter", "this_week": 1, "last_week": 2},
            {"song": "Broken", "this_week": 2},
        ],
    }
    monkeypatch.setattr("cue.discovery_providers.urlopen", lambda request, timeout: _source_response(payload, fetched))
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=tmp_path,
        session_secret="test-session-secret-that-is-long-enough",
        bootstrap_admin_username="owner",
        bootstrap_admin_password="correct-horse-battery-staple",
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "correct-horse-battery-staple"},
        )
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        collection = client.post("/api/v1/collections", headers=headers, json={"name": "Chart"}).json()
        response = client.post(
            f"/api/v1/collections/{collection['id']}/billboard-hot-100-previews",
            headers=headers,
            json={"configured_source": configured, "chart_date": "2026-08-01"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["adapter"] == "billboard_hot_100"
        assert body["counts"] == {"accepted": 1, "duplicate": 0, "rejected": 1}
        assert body["rows"][0] == {
            "position": 0,
            "rank": 1,
            "artists": ["Sabrina Carpenter"],
            "title": "Espresso",
            "status": "accepted",
            "error": None,
        }
        assert body["provenance"]["configured_url"] == configured
        assert body["provenance"]["fetched_url"] == fetched
        assert body["provenance"]["raw_source_json"] == payload
        assert client.post(f"/api/v1/source-snapshots/{body['id']}/approvals", headers=headers).status_code == 201


def test_billboard_only_accepts_raw_github_urls():
    assert billboard_source_url("https://raw.githubusercontent.com/example/charts/main") == (
        "https://raw.githubusercontent.com/example/charts/main/recent.json"
    )
    try:
        billboard_source_url("https://example.test/recent.json")
    except ValueError as exc:
        assert "raw.githubusercontent.com" in str(exc)
    else:
        raise AssertionError("expected an unsafe source URL to be rejected")


def test_xmplaylist_alt_nation_preview_preserves_provider_snapshot(monkeypatch, tmp_path):
    fetched = "https://xmplaylist.com/api/station/altnation"
    payload = {
        "channel": {"name": "Alt Nation", "deeplink": "altnation"},
        "results": [
            {
                "id": "play-1",
                "timestamp": "2099-01-01T00:00:00Z",
                "track": {"id": "track-1", "artists": ["The Beaches"], "title": "Edge of the Earth"},
            }
        ],
    }
    monkeypatch.setattr("cue.discovery_providers.urlopen", lambda request, timeout: _source_response(payload, fetched))
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=tmp_path,
        session_secret="test-session-secret-that-is-long-enough",
        bootstrap_admin_username="owner",
        bootstrap_admin_password="correct-horse-battery-staple",
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "correct-horse-battery-staple"},
        )
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        collection = client.post("/api/v1/collections", headers=headers, json={"name": "Alt Nation"}).json()
        response = client.post(
            f"/api/v1/collections/{collection['id']}/xmplaylist-previews",
            headers=headers,
            json={"station": "altnation", "window_hours": 24},
        )
    assert response.status_code == 201
    assert response.json()["adapter"] == "xmplaylist_recent"
    assert response.json()["rows"][0]["artists"] == ["The Beaches"]
    assert response.json()["provenance"]["station"] == "altnation"
    assert response.json()["provenance"]["raw_source_json"] == payload
