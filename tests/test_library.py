import json

import pytest

from cue.library import publish_atomically, safe_filename
from cue.models import CandidateAsset, Recording


def test_publication_is_atomic_and_never_replaces_existing_file(tmp_path):
    source = tmp_path / "stage" / "video.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video")

    destination = publish_atomically(source, tmp_path / "media", "Rush - Tom Sawyer [abc].mp4")

    assert destination.read_bytes() == b"video"
    assert not source.exists()
    assert not list((tmp_path / "media").glob("*.partial"))
    with pytest.raises(FileExistsError):
        publish_atomically(destination, tmp_path / "media", destination.name)


def test_filename_contains_provider_id_and_removes_path_separators():
    recording = Recording(artists_json=json.dumps(["AC/DC"]), title="Back/Black", canonical_key="acdc:back black")
    candidate = CandidateAsset(
        provider_id="a:b", recording_id=1, provider="youtube", url="https://example.test", title="x", score=1
    )

    assert safe_filename(recording, candidate, ".mp4") == "AC_DC - Back_Black [a_b].mp4"
