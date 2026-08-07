from cue.discovery import apply_discovery_recipe, parse_document


def test_provider_recipe_filters_orders_and_records_rules():
    document = {
        "items": [
            {"artists": ["The Beaches"], "title": "Edge", "rank": 2},
            {"artists": ["The Beaches"], "title": "Blame Brett", "rank": 1},
            {"artists": ["Other"], "title": "Edge", "rank": 3},
        ],
        "provenance": {"raw_source_json": {"data": "unchanged"}},
    }
    filtered = apply_discovery_recipe(
        document,
        {"discovery": {"include_artists": ["beaches"], "title_contains": ["e"], "order": "rank", "limit": 1}},
    )
    assert filtered["items"] == [{"artists": ["The Beaches"], "title": "Blame Brett", "rank": 1}]
    assert filtered["provenance"]["raw_source_json"] == {"data": "unchanged"}
    assert filtered["provenance"]["recipe_discovery_rules"]["order"] == "rank"
    assert parse_document(filtered).rows[0].title == "Blame Brett"
