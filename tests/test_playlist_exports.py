import json

from sqlalchemy import select

from cue.config import Settings
from cue.discovery import parse_document
from cue.models import CollectionEntry, CollectionResolution, PublishedAsset, Recording, User
from cue.services import (
    approve_playlist_export,
    approve_snapshot,
    create_collection,
    create_json_preview,
    create_playlist_export_preview,
)
from cue.worker import process_job


def test_m3u_export_preserves_order_and_reports_missing_items(session, tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    (media_root / "Rush - Tom Sawyer [abc].mp4").write_bytes(b"video")
    user = User(username="owner", password_hash="hash")
    session.add(user)
    session.flush()
    collection = create_collection(session, user, "Classic Rock", {})
    document = [
        {"artists": ["Rush"], "title": "Tom Sawyer"},
        {"artists": ["The Clash"], "title": "London Calling"},
    ]
    snapshot = create_json_preview(
        session, collection=collection, owner=user, document=document, preview=parse_document(document)
    )
    approve_snapshot(session, snapshot, user)
    entries = list(session.scalars(select(CollectionEntry).order_by(CollectionEntry.ordinal)))
    rush = session.get(Recording, entries[0].recording_id)
    session.add(
        PublishedAsset(
            recording_id=rush.id,
            relative_path="Rush - Tom Sawyer [abc].mp4",
            container="mp4",
            byte_size=5,
        )
    )
    session.add(CollectionResolution(collection_entry_id=entries[0].id, status="published"))
    session.add(CollectionResolution(collection_entry_id=entries[1].id, status="review"))
    session.flush()

    playlist_export = create_playlist_export_preview(
        session,
        collection=collection,
        owner=user,
        name=None,
        media_root=media_root,
        m3u_path_prefix="/mnt/music-videos",
    )
    manifest = json.loads(playlist_export.manifest_json)
    assert manifest["resolved"] == [
        {
            "display_name": "Rush - Tom Sawyer",
            "ordinal": 1,
            "playlist_path": "/mnt/music-videos/Rush - Tom Sawyer [abc].mp4",
            "recording_id": rush.id,
            "relative_path": "Rush - Tom Sawyer [abc].mp4",
        }
    ]
    assert manifest["missing"][0]["display_name"] == "The Clash - London Calling"
    assert manifest["missing"][0]["reason"] == "review"

    job = approve_playlist_export(session, playlist_export, user)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cue.sqlite3'}",
        media_root=media_root,
        export_root=tmp_path / "exports",
        session_secret="test-session-secret-that-is-long-enough",
    )
    process_job(session, job.id, settings)

    assert playlist_export.status == "published"
    m3u8 = (settings.export_root / playlist_export.m3u8_relative_path).read_text()
    assert m3u8 == "#EXTM3U\n#EXTINF:-1,Rush - Tom Sawyer\n/mnt/music-videos/Rush - Tom Sawyer [abc].mp4\n"
    report = json.loads((settings.export_root / playlist_export.report_relative_path).read_text())
    assert report["missing"] == manifest["missing"]
