from cue.scoring import score_candidate


def test_official_video_scores_above_review_formats():
    official = score_candidate(["Rush"], "Tom Sawyer", "Rush - Tom Sawyer (Official Video)", "Rush")
    lyric = score_candidate(["Rush"], "Tom Sawyer", "Rush - Tom Sawyer (Lyric Video)", "Rush")
    assert official.score > lyric.score
    assert lyric.classifications == ["lyric"]
