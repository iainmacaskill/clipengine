from clipengine.campaigns.rules import parse_rules

BRIEF = """\
Clip our Valorant streams! Post to TikTok and YouTube Shorts.
Must include #ValorantClips #GG and tag @brandco in the caption.
Clips must be at least 30 seconds.
- No watermarks from other apps
- Do not use AI voiceovers
Source VODs: https://twitch.tv/brandco/videos
"""


def test_extracts_hashtags_and_mentions():
    check = parse_rules(BRIEF)
    assert check.hashtags == ["ValorantClips", "GG"]
    assert "brandco" in check.mentions


def test_mention_at_sentence_end_drops_trailing_dot():
    assert parse_rules("tag @neon. Then post.").mentions == ["neon"]


def test_extracts_min_duration():
    assert parse_rules(BRIEF).min_duration_s == 30.0


def test_duration_variants():
    assert parse_rules("minimum 1 minute").min_duration_s == 60.0
    assert parse_rules("videos of 45+ seconds").min_duration_s == 45.0
    assert parse_rules("keep it under 3 minutes").max_duration_s == 180.0
    check = parse_rules("clips should be 30-60 seconds long")
    assert (check.min_duration_s, check.max_duration_s) == (30.0, 60.0)


def test_extracts_platforms():
    assert parse_rules(BRIEF).platforms == ["tiktok", "youtube"]
    assert parse_rules("post Reels only").platforms == ["instagram"]


def test_banned_and_required_lines():
    check = parse_rules(BRIEF)
    assert any("watermarks" in b for b in check.banned)
    assert any("AI voiceovers" in b for b in check.banned)
    assert any("#ValorantClips" in r for r in check.required)
    # banned lines are not double-counted as required
    assert not any("watermarks" in r for r in check.required)


def test_extracts_source_links():
    assert parse_rules(BRIEF).links == ["https://twitch.tv/brandco/videos"]


def test_empty_text_is_simple():
    check = parse_rules("   ")
    assert check.complexity == 0 and check.simplicity == 1.0


def test_simplicity_decreases_with_requirements():
    simple = parse_rules("Have fun clipping!")
    complex_ = parse_rules(BRIEF)
    assert complex_.complexity > simple.complexity
    assert complex_.simplicity < simple.simplicity


def test_parser_never_invents_requirements():
    check = parse_rules("Great campaign, huge budget, easy money.")
    assert check.hashtags == [] and check.mentions == []
    assert check.min_duration_s is None and check.banned == []
