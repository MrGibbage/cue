import pytest

from cue.discovery import MAX_JSON_UPLOAD_BYTES, parse_uploaded_document


def test_uploaded_song_list_requires_utf8_json_and_a_bounded_document():
    assert parse_uploaded_document(b'[{"artists":["Rush"],"title":"Tom Sawyer"}]')[0]["title"] == "Tom Sawyer"
    with pytest.raises(ValueError, match="2 MiB"):
        parse_uploaded_document(b" " * (MAX_JSON_UPLOAD_BYTES + 1))
    with pytest.raises(UnicodeDecodeError):
        parse_uploaded_document(b"\xff")
    with pytest.raises(ValueError, match="array or an object"):
        parse_uploaded_document(b'"not a song list"')
