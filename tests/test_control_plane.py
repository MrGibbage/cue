from fastapi.testclient import TestClient

from cue.api import create_app
from cue.config import Settings


def make_client(tmp_path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=tmp_path,
        session_secret="test-session-secret-that-is-long-enough",
        bootstrap_admin_username="owner",
        bootstrap_admin_password="correct-horse-battery-staple",
    )
    return TestClient(create_app(settings), base_url="https://testserver")


def login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_login_token_collection_and_audit(tmp_path):
    with make_client(tmp_path) as client:
        csrf_token = login(client)
        headers = {"X-CSRF-Token": csrf_token}

        collection = client.post(
            "/api/v1/collections",
            headers=headers,
            json={"name": "Classic Rock", "recipe": {"video_profile": "strict"}},
        )
        assert collection.status_code == 201
        assert collection.json() == {"id": 1, "name": "Classic Rock", "version": 1}

        token = client.post(
            "/api/v1/tokens",
            headers=headers,
            json={"name": "test automation", "scopes": ["collections:read"]},
        )
        assert token.status_code == 201
        raw_token = token.json()["token"]
        assert raw_token.startswith("cue_")

        api_client = TestClient(
            create_app(
                Settings(
                    database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
                    media_root=tmp_path,
                    session_secret="test-session-secret-that-is-long-enough",
                )
            )
        )
        with api_client:
            response = api_client.get("/api/v1/collections", headers={"Authorization": f"Bearer {raw_token}"})
        assert response.status_code == 200
        assert response.json() == [{"id": 1, "name": "Classic Rock"}]

        denied = api_client.post(
            "/api/v1/collections",
            headers={"Authorization": f"Bearer {raw_token}"},
            json={"name": "Not permitted"},
        )
        assert denied.status_code == 403

        tokens = client.get("/api/v1/tokens", headers=headers)
        assert tokens.status_code == 200
        assert tokens.json()[0]["name"] == "test automation"

        events = client.get("/api/v1/audit-events", headers=headers)
        assert events.status_code == 200
        assert {event["action"] for event in events.json()} >= {
            "user.bootstrap_created",
            "user.logged_in",
            "collection.created",
            "token.created",
        }

        revoked = client.delete(f"/api/v1/tokens/{token.json()['id']}", headers=headers)
        assert revoked.status_code == 204
        assert (
            api_client.get("/api/v1/collections", headers={"Authorization": f"Bearer {raw_token}"}).status_code == 401
        )


def test_mutations_require_csrf_for_sessions(tmp_path):
    with make_client(tmp_path) as client:
        login(client)
        response = client.post("/api/v1/collections", json={"name": "No CSRF"})
    assert response.status_code == 403
