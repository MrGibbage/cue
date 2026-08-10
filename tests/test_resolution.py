import json

from cue.models import (
    CandidateAsset,
    Collection,
    CollectionEntry,
    CollectionVersion,
    Recording,
    SourceRow,
    SourceSnapshot,
    User,
)
from cue.services import decide_resolution, queue_candidate_download


def test_clear_official_video_is_auto_selected_and_queued(session):
    user = User(username="owner", password_hash="hash")
    recording = Recording(artists_json=json.dumps(["Rush"]), title="Tom Sawyer", canonical_key="rush:tom sawyer")
    session.add_all([user, recording])
    session.flush()
    collection = Collection(owner_id=user.id, name="Test")
    session.add(collection)
    session.flush()
    version = CollectionVersion(collection_id=collection.id, version=1, created_by_id=user.id)
    session.add(version)
    session.flush()
    snapshot = SourceSnapshot(
        collection_id=collection.id,
        collection_version_id=version.id,
        adapter="json",
        raw_document_json="[]",
        created_by_id=user.id,
    )
    session.add(snapshot)
    session.flush()
    row = SourceRow(snapshot_id=snapshot.id, source_position=0, status="accepted", raw_json="{}")
    session.add(row)
    session.flush()
    entry = CollectionEntry(
        collection_version_id=version.id, recording_id=recording.id, source_row_id=row.id, ordinal=1
    )
    candidate = CandidateAsset(
        recording_id=recording.id,
        provider="youtube",
        provider_id="abc",
        url="https://example.test/abc",
        title="Rush - Tom Sawyer (Official Music Video)",
        score=100,
        classifications_json='["official_music_video"]',
        reasons_json="[]",
    )
    session.add_all([entry, candidate])
    session.flush()

    resolution = decide_resolution(session, entry, [candidate])
    job = queue_candidate_download(session, owner=user, resolution=resolution)

    assert resolution.status == "auto_selected"
    assert resolution.candidate_asset_id == candidate.id
    assert job.kind == "download_candidate"


def test_unclear_candidates_require_review(session):
    user = User(username="owner", password_hash="hash")
    recording = Recording(artists_json=json.dumps(["Rush"]), title="Tom Sawyer", canonical_key="rush:tom sawyer")
    session.add_all([user, recording])
    session.flush()
    collection = Collection(owner_id=user.id, name="Test")
    session.add(collection)
    session.flush()
    version = CollectionVersion(collection_id=collection.id, version=1, created_by_id=user.id)
    session.add(version)
    session.flush()
    snapshot = SourceSnapshot(
        collection_id=collection.id,
        collection_version_id=version.id,
        adapter="json",
        raw_document_json="[]",
        created_by_id=user.id,
    )
    session.add(snapshot)
    session.flush()
    row = SourceRow(snapshot_id=snapshot.id, source_position=0, status="accepted", raw_json="{}")
    session.add(row)
    session.flush()
    entry = CollectionEntry(
        collection_version_id=version.id, recording_id=recording.id, source_row_id=row.id, ordinal=1
    )
    candidate = CandidateAsset(
        recording_id=recording.id,
        provider="youtube",
        provider_id="lyric",
        url="https://example.test/lyric",
        title="Rush - Tom Sawyer (Lyric Video)",
        score=50,
        classifications_json='["lyric"]',
        reasons_json="[]",
    )
    session.add_all([entry, candidate])
    session.flush()

    resolution = decide_resolution(session, entry, [candidate])

    assert resolution.status == "review"
    assert resolution.candidate_asset_id is None


def test_wrong_song_official_candidate_cannot_block_clear_match(session):
    user = User(username="owner", password_hash="hash")
    recording = Recording(artists_json=json.dumps(["Van Halen"]), title="Jump", canonical_key="van halen:jump")
    session.add_all([user, recording])
    session.flush()
    collection = Collection(owner_id=user.id, name="Test")
    session.add(collection)
    session.flush()
    version = CollectionVersion(collection_id=collection.id, version=1, created_by_id=user.id)
    session.add(version)
    session.flush()
    snapshot = SourceSnapshot(
        collection_id=collection.id,
        collection_version_id=version.id,
        adapter="json",
        raw_document_json="[]",
        created_by_id=user.id,
    )
    session.add(snapshot)
    session.flush()
    row = SourceRow(snapshot_id=snapshot.id, source_position=0, status="accepted", raw_json="{}")
    session.add(row)
    session.flush()
    entry = CollectionEntry(
        collection_version_id=version.id, recording_id=recording.id, source_row_id=row.id, ordinal=1
    )
    official = CandidateAsset(
        recording_id=recording.id,
        provider="youtube",
        provider_id="jump",
        url="https://example.test/jump",
        title="Van Halen - Jump (Official Music Video)",
        score=100,
        classifications_json='["official_music_video"]',
        reasons_json="[]",
    )
    wrong_song = CandidateAsset(
        recording_id=recording.id,
        provider="youtube",
        provider_id="panama",
        url="https://example.test/panama",
        title="Van Halen - Panama (Official Music Video)",
        score=0,
        classifications_json='["wrong_song"]',
        reasons_json="[]",
    )
    session.add_all([entry, official, wrong_song])
    session.flush()

    resolution = decide_resolution(session, entry, [official, wrong_song])

    assert resolution.status == "auto_selected"
    assert resolution.candidate_asset_id == official.id


def test_no_candidates_leaves_recording_unresolved(session):
    user = User(username="owner", password_hash="hash")
    recording = Recording(artists_json=json.dumps(["Rush"]), title="Tom Sawyer", canonical_key="rush:tom sawyer")
    session.add_all([user, recording])
    session.flush()
    collection = Collection(owner_id=user.id, name="Test")
    session.add(collection)
    session.flush()
    version = CollectionVersion(collection_id=collection.id, version=1, created_by_id=user.id)
    session.add(version)
    session.flush()
    snapshot = SourceSnapshot(
        collection_id=collection.id,
        collection_version_id=version.id,
        adapter="json",
        raw_document_json="[]",
        created_by_id=user.id,
    )
    session.add(snapshot)
    session.flush()
    row = SourceRow(snapshot_id=snapshot.id, source_position=0, status="accepted", raw_json="{}")
    session.add(row)
    session.flush()
    entry = CollectionEntry(
        collection_version_id=version.id,
        recording_id=recording.id,
        source_row_id=row.id,
        ordinal=1,
    )
    session.add(entry)
    session.flush()

    resolution = decide_resolution(session, entry, [])

    assert resolution.status == "unresolved"
