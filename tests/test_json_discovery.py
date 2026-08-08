from fastapi.testclient import TestClient

from cue.api import create_app
from cue.config import Settings
from cue.discovery import MAX_JSON_DOCUMENT_BYTES


def test_json_preview_and_approval(tmp_path):
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
        collection = client.post("/api/v1/collections", headers=headers, json={"name": "Classic Rock"})
        preview = client.post(
            f"/api/v1/collections/{collection.json()['id']}/json-previews",
            headers=headers,
            json={
                "document": {
                    "source": "External list",
                    "items": [
                        {"artists": ["The Clash"], "title": "London Calling", "rank": 2},
                        {"artists": ["The Clash"], "title": "London Calling", "rank": 3},
                        {"artists": ["AC/DC"], "title": "Back in Black", "rank": 1},
                        {"artists": "Bad shape", "title": "Rejected"},
                    ],
                }
            },
        )
        assert preview.status_code == 201
        assert preview.json()["counts"] == {"accepted": 2, "duplicate": 1, "rejected": 1}
        assert preview.json()["rows"][1]["status"] == "duplicate"
        snapshot_id = preview.json()["id"]

        approval = client.post(f"/api/v1/source-snapshots/{snapshot_id}/approvals", headers=headers)
        assert approval.status_code == 201
        assert approval.json()["status"] == "approved"
        assert client.post(f"/api/v1/source-snapshots/{snapshot_id}/approvals", headers=headers).status_code == 409

        snapshot = client.get(f"/api/v1/source-snapshots/{snapshot_id}")
        assert snapshot.status_code == 200
        assert snapshot.json()["status"] == "approved"


def test_json_upload_preview(tmp_path):
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
        collection = client.post("/api/v1/collections", headers=headers, json={"name": "Upload"})
        response = client.post(
            f"/api/v1/collections/{collection.json()['id']}/json-upload-previews",
            headers=headers,
            files={"file": ("songs.json", b'[{"artists":["Rush"],"title":"Tom Sawyer"}]', "application/json")},
        )
    assert response.status_code == 201
    assert response.json()["counts"]["accepted"] == 1


def test_json_preview_without_accepted_songs_cannot_be_approved(tmp_path):
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
        collection = client.post("/api/v1/collections", headers=headers, json={"name": "Invalid list"})
        preview = client.post(
            f"/api/v1/collections/{collection.json()['id']}/json-previews",
            headers=headers,
            json={"document": [{"artists": [], "title": "Missing artist"}]},
        )
        assert preview.status_code == 201
        assert preview.json()["counts"] == {"accepted": 0, "duplicate": 0, "rejected": 1}

        approval = client.post(f"/api/v1/source-snapshots/{preview.json()['id']}/approvals", headers=headers)
        assert approval.status_code == 409
        assert approval.json()["detail"] == "A preview needs at least one accepted song before it can be approved"


def test_api_json_preview_rejects_documents_over_the_shared_limit(tmp_path):
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
        collection = client.post("/api/v1/collections", headers=headers, json={"name": "Large list"})
        response = client.post(
            f"/api/v1/collections/{collection.json()['id']}/json-previews",
            headers=headers,
            json={"document": [{"artists": ["Rush"], "title": "Tom Sawyer", "notes": "x" * MAX_JSON_DOCUMENT_BYTES}]},
        )
    assert response.status_code == 422
    assert response.json()["detail"] == "JSON document exceeds the 2 MiB limit"
