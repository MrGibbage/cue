import json
from types import SimpleNamespace

import pytest

from cue.providers import search_youtube, validate_video


def test_youtube_search_is_metadata_only(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=(
                '{"id":"abc","webpage_url":"https://youtube.test/watch?v=abc",'
                '"title":"Rush - Tom Sawyer","uploader":"Rush","duration":281}\n'
            ),
        )

    monkeypatch.setattr("cue.providers.subprocess.run", fake_run)
    result = search_youtube(["Rush"], "Tom Sawyer")
    assert result[0].provider_id == "abc"
    assert "--dump-json" in seen["command"]
    assert not any("download" in part for part in seen["command"])


def test_video_validation_rejects_audio_only_output(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "cue.providers.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({"streams": []})),
    )

    with pytest.raises(RuntimeError, match="no video stream"):
        validate_video(tmp_path / "audio.mp4")
