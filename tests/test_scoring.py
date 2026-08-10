from cue.scoring import score_candidate


def test_official_video_scores_above_review_formats():
    official = score_candidate(["Rush"], "Tom Sawyer", "Rush - Tom Sawyer (Official Video)", "Rush")
    lyric = score_candidate(["Rush"], "Tom Sawyer", "Rush - Tom Sawyer (Lyric Video)", "Rush")
    assert official.score > lyric.score
    assert lyric.classifications == ["lyric"]


def test_artist_channel_official_video_outranks_untrusted_reupload():
    official = score_candidate(
        ["Van Halen"], "Jump", "Van Halen - Jump (Official Music Video) [HD]", "Van Halen"
    )
    reupload = score_candidate(["Van Halen"], "Jump", "Van Halen - Jump (Official 4K Video)", "REMASTERED IN!")

    assert official.score == 100
    assert reupload.score < official.score
    assert official.classifications == ["official_music_video"]


def test_wrong_song_cannot_be_classified_as_an_official_video():
    wrong_song = score_candidate(
        ["Van Halen"], "Jump", "Van Halen - Panama (Official Music Video)", "Van Halen"
    )

    assert wrong_song.score == 0
    assert "wrong_song" in wrong_song.classifications
    assert "official_music_video" not in wrong_song.classifications
