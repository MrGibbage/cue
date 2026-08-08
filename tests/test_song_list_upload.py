import pytest

from cue.discovery import (
    MAX_JSON_DOCUMENT_BYTES,
    MAX_JSON_UPLOAD_BYTES,
    MAX_SOURCE_NAME_CHARS,
    MAX_SQLITE_INTEGER,
    parse_document,
    parse_uploaded_document,
)


def test_uploaded_song_list_requires_utf8_json_and_a_bounded_document():
    assert parse_uploaded_document(b'[{"artists":["Rush"],"title":"Tom Sawyer"}]')[0]["title"] == "Tom Sawyer"
    with pytest.raises(ValueError, match="2 MiB"):
        parse_uploaded_document(b" " * (MAX_JSON_UPLOAD_BYTES + 1))
    with pytest.raises(UnicodeDecodeError):
        parse_uploaded_document(b"\xff")
    with pytest.raises(ValueError, match="array or an object"):
        parse_uploaded_document(b'"not a song list"')


def test_parsed_song_list_uses_the_same_size_limit_as_uploads():
    with pytest.raises(ValueError, match="2 MiB"):
        parse_document([{"artists": ["Rush"], "title": "Tom Sawyer", "notes": "x" * MAX_JSON_DOCUMENT_BYTES}])


def test_song_list_bounds_metadata_and_rejects_only_invalid_rows():
    with pytest.raises(ValueError, match="source must be a string"):
        parse_document({"source": "x" * (MAX_SOURCE_NAME_CHARS + 1), "items": []})

    preview = parse_document(
        [
            {"artists": ["Rush"], "title": "Tom Sawyer", "rank": MAX_SQLITE_INTEGER + 1},
            {"artists": ["Rush"], "title": "Limelight", "rank": 2},
        ]
    )
    assert preview.rows[0].status == "rejected"
    assert preview.rows[0].error == "rank must be a SQLite-compatible integer when supplied"
    assert preview.rows[1].status == "accepted"
