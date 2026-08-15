import json

from sqlalchemy import select

from cue.models import (
    CandidateAsset,
    ChannelTrust,
    Collection,
    CollectionEntry,
    CollectionVersion,
    Job,
    Recording,
    SourceRow,
    SourceSnapshot,
    User,
)
from cue.services import (
    assess_candidate,
    decide_resolution,
    owner_channel_trusts,
    queue_candidate_download,
    queue_collection_reassessment,
)


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


def test_owner_confirmed_channel_can_make_an_otherwise_safe_candidate_recommendable(session):
    user = User(username="owner", password_hash="hash")
    recording = Recording(
        artists_json=json.dumps(["Foreigner"]), title="I Want to Know What Love Is", canonical_key="foreigner:love"
    )
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
        provider_id="rhino",
        url="https://example.test/rhino",
        title="Foreigner - I Want to Know What Love Is (Official Music Video)", uploader="RHINO",
        uploader_id="UCWEtnEiVwUy7mwFeshyAWLA",
        score=85,
        classifications_json='["official_music_video"]',
        reasons_json="[]",
    )
    session.add_all([entry, candidate])
    session.flush()

    before_score, _, _ = assess_candidate(candidate, {})
    assert before_score == 95
    assert decide_resolution(session, entry, [candidate]).status == "review"

    session.add(
        ChannelTrust(
            owner_id=user.id,
            provider="youtube",
            channel_id=candidate.uploader_id,
            channel_name="RHINO",
            authority="label",
        )
    )
    session.flush()
    trusts = owner_channel_trusts(session, user.id)
    after_score, _, reasons = assess_candidate(candidate, {}, trusts)
    resolution = decide_resolution(session, entry, [candidate], {}, trusts)

    assert after_score == 120
    assert "trusted label channel" in reasons
    assert resolution.status == "auto_selected"
    # Re-ranking only chooses a recommendation; queueing remains a separate explicit action.
    assert session.scalar(select(Job)) is None


def test_collection_reassessment_job_is_idempotent_while_pending(session):
    user = User(username="owner", password_hash="hash")
    session.add(user)
    session.flush()
    collection = Collection(owner_id=user.id, name="Test")
    session.add(collection)
    session.flush()

    first = queue_collection_reassessment(session, owner=user, collection=collection)
    second = queue_collection_reassessment(session, owner=user, collection=collection)

    assert first.id == second.id
    assert first.kind == "reassess_collection_candidates"


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


def test_channel_only_policy_excludes_other_candidates(session):
    candidate = CandidateAsset(
        recording_id=1, provider="youtube", provider_id="fan", url="https://example.test/fan", title="Song", score=90,
        uploader_id="UC-fan", classifications_json='["official_music_video"]', reasons_json="[]"
    )

    score, allowed, reasons = assess_candidate(candidate, {"channel_mode": "only", "channel_ids": ["UC-rhino"]})

    assert score == 100
    assert not allowed
    assert reasons == ["not from an allowed channel", "preferred format: official music video"]
