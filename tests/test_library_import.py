from fastapi.testclient import TestClient
from sqlalchemy import select

from cue.api import create_app
from cue.config import Settings
from cue.discovery import parse_document
from cue.library import parse_library_filename
from cue.models import CollectionEntry, CollectionResolution, PublishedAsset, Recording, User
from cue.services import approve_snapshot, create_collection, create_json_preview
from cue.worker import process_job


def test_filename_parser_handles_descriptor_year_and_multiple_artists():
    parsed = parse_library_filename(
        "Yeah Yeah Yeahs & Perfume Genius - Spitting Off the Edge (Official Video) [2022].mp4"
    )

    assert parsed.artists == ["Yeah Yeah Yeahs", "Perfume Genius"]
    assert parsed.title == "Spitting Off the Edge"
    assert parsed.descriptor == "Official Video"
    assert parsed.year == 2022
    assert parsed.error is None


def test_filename_parser_requires_artist_title_separator():
    parsed = parse_library_filename("unstructured-file.mp4")

    assert parsed.error == "Expected 'Artist - Title' filename format"
    assert parsed.canonical_key is None


def test_existing_library_preview_and_approval_are_safe_and_idempotent(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    managed = media_root / "Yellowcard - Better Days (Official Music Video) [2025].mp4"
    managed.write_bytes(b"video")
    (media_root / "unstructured-file.mkv").write_bytes(b"video")
    (media_root / ".cue-staging").mkdir()
    (media_root / ".cue-staging" / "ignored.mp4").write_bytes(b"video")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=media_root,
        session_secret="test-session-secret-that-is-long-enough",
        bootstrap_admin_username="owner",
        bootstrap_admin_password="correct-horse-battery-staple",
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": "correct-horse-battery-staple"}
        )
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        preview = client.post("/api/v1/library-imports/previews", headers=headers, json={"source_name": "My library"})

        assert preview.status_code == 201
        assert preview.json()["counts"] == {"accepted": 1, "already_imported": 0, "review": 1, "imported": 0}
        assert managed.read_bytes() == b"video"
        library_import_id = preview.json()["id"]
        paged = client.get(f"/api/v1/library-imports/{library_import_id}?page_size=1", headers=headers)
        assert paged.json()["total_rows"] == 2
        assert paged.json()["counts"] == {"accepted": 1, "already_imported": 0, "review": 1, "imported": 0}
        assert len(paged.json()["rows"]) == 1

        approval = client.post(f"/api/v1/library-imports/{library_import_id}/approvals", headers=headers)
        assert approval.status_code == 200
        assert approval.json()["imported"] == 1
        assert managed.exists()
        assert client.post(f"/api/v1/library-imports/{library_import_id}/approvals", headers=headers).status_code == 409

        assets = client.get("/api/v1/library/assets")
        assert assets.status_code == 200
        assert assets.json()["total_rows"] == 1
        assert assets.json()["rows"][0]["relative_path"] == managed.name
        assert assets.json()["rows"][0]["source"] == "library_import"

        second_preview = client.post("/api/v1/library-imports/previews", headers=headers, json={})
        assert second_preview.status_code == 201
        assert second_preview.json()["counts"]["already_imported"] == 1


def test_collection_reuses_imported_recording_without_a_provider_search(session, tmp_path, monkeypatch):
    user = User(username="owner", password_hash="hash")
    session.add(user)
    session.flush()
    collection = create_collection(session, user, "Existing", {})
    preview = parse_document([{"artists": ["Rush"], "title": "Tom Sawyer"}])
    snapshot = create_json_preview(
        session, collection=collection, owner=user, document=preview.rows[0].raw, preview=preview
    )
    job = approve_snapshot(session, snapshot, user)
    recording = session.scalar(select(Recording).where(Recording.canonical_key == "rush :: tom sawyer"))
    session.add(
        PublishedAsset(
            recording_id=recording.id,
            relative_path="Rush - Tom Sawyer [existing].mp4",
            container="mp4",
            byte_size=5,
        )
    )
    session.flush()
    def no_search(*_):
        raise AssertionError("should not search")

    monkeypatch.setattr("cue.worker.search_youtube", no_search)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'worker.sqlite3'}",
        media_root=tmp_path,
        session_secret="test-session-secret-that-is-long-enough",
    )

    process_job(session, job.id, settings)

    entry = session.scalar(select(CollectionEntry))
    resolution = session.scalar(select(CollectionResolution))
    assert entry.status == "resolved"
    assert resolution.status == "published"
