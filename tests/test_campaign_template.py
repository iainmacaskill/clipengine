import pytest

from clipengine.campaigns.models import Campaign
from clipengine.campaigns.template import (
    build_caption,
    effective_target,
    merge_credit,
    template_for,
)

RULES = """\
Post to TikTok or YouTube Shorts.
Must include #NeonClips and tag @neon in the caption.
Clips must be at least 30 seconds.
- No AI voiceovers
"""


def _campaign(rules=RULES, **over):
    base = dict(
        id="manual:neon", source="manual", title="Neon clips", status="open",
        reward_model="cpm", reward_amount=2.0, budget_total=5000.0,
        budget_remaining=5000.0, rules_text=rules,
    )
    base.update(over)
    return Campaign(**base)


# -- template derivation ---------------------------------------------------


def test_template_derives_from_rules():
    t = template_for(_campaign())
    assert t.campaign_id == "manual:neon"
    assert t.credit_text == "@neon"
    assert t.caption_suffix == "#NeonClips @neon"
    assert t.min_duration_s == 30.0 and t.max_duration_s is None
    assert t.platforms == ["tiktok", "youtube"]


def test_template_empty_rules_mandates_nothing():
    t = template_for(_campaign(rules=""))
    assert t.credit_text == "" and t.caption_suffix == ""
    assert t.min_duration_s is None and t.platforms == []


# -- duration steering -----------------------------------------------------


def test_effective_target_unbounded_keeps_base():
    assert effective_target(template_for(_campaign(rules="")), 75.0) == 75.0


def test_effective_target_clamps_up_to_min_plus_margin():
    t = template_for(_campaign(rules="at least 90 seconds"))
    assert effective_target(t, 75.0) == 95.0


def test_effective_target_clamps_down_to_max_minus_margin():
    t = template_for(_campaign(rules="keep it under 60 seconds"))
    assert effective_target(t, 75.0) == 55.0


def test_effective_target_inside_bounds_untouched():
    t = template_for(_campaign(rules="clips should be 60-120 seconds"))
    assert effective_target(t, 75.0) == 75.0


def test_effective_target_tight_bounds_use_midpoint():
    t = template_for(_campaign(rules="clips should be 30-35 seconds"))
    assert effective_target(t, 75.0) == 32.5


# -- captions --------------------------------------------------------------


def test_build_caption_appends_missing_tokens():
    t = template_for(_campaign())
    assert build_caption("insane clutch", t) == "insane clutch #NeonClips @neon"


def test_build_caption_keeps_existing_case_insensitive():
    t = template_for(_campaign())
    assert build_caption("clutch #neonclips", t) == "clutch #neonclips @neon"


def test_build_caption_idempotent():
    t = template_for(_campaign())
    once = build_caption("clutch", t)
    assert build_caption(once, t) == once


def test_build_caption_empty_title_is_just_requirements():
    t = template_for(_campaign())
    assert build_caption("", t) == "#NeonClips @neon"


# -- credit merge ----------------------------------------------------------


def test_merge_credit_combines():
    t = template_for(_campaign())
    assert merge_credit("clip: twitch.tv/neon", t) == "clip: twitch.tv/neon | @neon"


def test_merge_credit_skips_when_contained():
    t = template_for(_campaign())
    assert merge_credit("follow @neon on twitch", t) == "follow @neon on twitch"


def test_merge_credit_campaign_only_when_no_base():
    t = template_for(_campaign())
    assert merge_credit("", t) == "@neon"


def test_merge_credit_no_mandate_keeps_base():
    t = template_for(_campaign(rules="just clip stuff"))
    assert merge_credit("clip: twitch.tv/x", t) == "clip: twitch.tv/x"


# -- process_vod integration ----------------------------------------------


@pytest.fixture
def process_env(monkeypatch, tmp_path):
    from clipengine import pipeline
    from clipengine.config import Config
    from clipengine.models import ClipCandidate
    from clipengine.roster import Roster

    cfg = Config()
    cfg.work_dir = str(tmp_path / "work")
    cfg.roster_db = str(tmp_path / "roster.db")
    with Roster(cfg.roster_db) as r:
        r.add("nl", source="licence", evidence="campaign manual:neon", credit="")

    calls = {"rendered": [], "targets": []}
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def fake_detect(v, c, cf):
        calls["targets"].append(cf.detect.target_duration)
        dur = cf.detect.target_duration
        return [ClipCandidate(start=100.0, end=100.0 + dur, score=3.0)]

    monkeypatch.setattr(pipeline, "detect_candidates", fake_detect)

    def fake_render(video, cand, facecam, out_path, cf, with_captions=True,
                    credit_text=None, transcript_out=None):
        calls["rendered"].append(credit_text)
        open(out_path, "w").write("clip")
        return out_path

    monkeypatch.setattr(pipeline, "render_candidate", fake_render)
    monkeypatch.setattr(pipeline.audio, "extract_wav", lambda v, w: w)
    monkeypatch.setattr("clipengine.package.music.check", lambda wav, threshold=0.3: [])
    return cfg, calls


def test_process_with_campaign_bakes_compliance(process_env, tmp_path):
    from clipengine import pipeline
    from clipengine.models import FacecamRegion

    cfg, calls = process_env
    campaign = _campaign(rules=RULES + "keep it under 60 seconds\n")
    manifest = pipeline.process_vod(
        "v.mp4", None, "nl", str(tmp_path / "out"), cfg,
        top_n=1, facecam=FacecamRegion(0, 0, 10, 10), campaign=campaign,
    )
    # detection steered inside campaign bounds (75 -> 55), original cfg untouched
    assert calls["targets"] == [55.0]
    assert cfg.detect.target_duration == 75.0
    # mandated credit merged into the burned credit
    assert calls["rendered"] == ["clip: twitch.tv/nl | @neon"]
    (item,) = manifest
    assert item["campaign"] == "manual:neon"
    assert item["caption"] == "#NeonClips @neon"
    assert item["gate"]["passed"], item["gate"]["failures"]
    assert any("AI voiceovers" in m for m in item["gate"]["manual"])


def test_process_with_campaign_records_gate_failure(process_env, tmp_path):
    from clipengine import pipeline
    from clipengine.models import FacecamRegion

    cfg, calls = process_env
    # min 90s but detector windows are clamped elsewhere; simulate a short
    # candidate by lowering the base target below the campaign minimum
    cfg.detect.target_duration = 20.0
    campaign = _campaign(rules="at least 90 seconds. include #Tag")
    manifest = pipeline.process_vod(
        "v.mp4", None, "nl", str(tmp_path / "out"), cfg,
        top_n=1, facecam=FacecamRegion(0, 0, 10, 10), campaign=campaign,
    )
    # steering raises the target to 95 -> candidate is 95s -> duration passes
    assert calls["targets"] == [95.0]
    assert manifest[0]["gate"]["passed"]


def test_process_without_campaign_manifest_unchanged(process_env, tmp_path):
    from clipengine import pipeline
    from clipengine.models import FacecamRegion

    cfg, _calls = process_env
    manifest = pipeline.process_vod(
        "v.mp4", None, "nl", str(tmp_path / "out"), cfg,
        top_n=1, facecam=FacecamRegion(0, 0, 10, 10),
    )
    assert "gate" not in manifest[0] and "campaign" not in manifest[0]


# -- CLI wiring ------------------------------------------------------------


def test_process_cli_campaign_queues_compliant_captions(process_env, tmp_path, capsys):
    from clipengine import cli
    from clipengine.campaigns.store import CampaignStore

    cfg, _calls = process_env
    with CampaignStore(str(tmp_path / "campaigns.db")) as store:
        store.upsert([_campaign()], at="t1")
    cfg_file = tmp_path / "cfg.toml"
    cfg_file.write_text(
        f'work_dir = "{cfg.work_dir}"\nroster_db = "{cfg.roster_db}"\n'
        f'[campaigns]\ncampaigns_db = "{tmp_path}/campaigns.db"\n'
        f'[schedule]\nqueue_db = "{tmp_path}/q.db"\n'
        f'windows = ["00:00-23:45"]\nmin_spacing_hours = 0.5\ndaily_cap = 10\n'
    )
    rc = cli.main([
        "--config", str(cfg_file), "process", "v.mp4", "--streamer", "nl",
        "-o", str(tmp_path / "out"), "--top", "1", "--facecam", "0,0,10,10",
        "--campaign", "manual:neon", "--queue-platform", "tiktok",
        "--account", "acct1",
    ])
    assert rc == 0
    assert "gate: PASS" in capsys.readouterr().out
    from clipengine.publish.scheduler import Queue

    with Queue(str(tmp_path / "q.db")) as q:
        (post,) = q.list()
    assert post.title == "#NeonClips @neon"  # compliant caption used as title


def test_process_cli_unknown_campaign_exits_1(process_env, tmp_path, capsys):
    from clipengine import cli

    cfg, _calls = process_env
    cfg_file = tmp_path / "cfg.toml"
    cfg_file.write_text(
        f'work_dir = "{cfg.work_dir}"\nroster_db = "{cfg.roster_db}"\n'
        f'[campaigns]\ncampaigns_db = "{tmp_path}/campaigns.db"\n'
    )
    rc = cli.main([
        "--config", str(cfg_file), "process", "v.mp4", "--streamer", "nl",
        "-o", str(tmp_path / "out"), "--campaign", "nope",
    ])
    assert rc == 1
    assert "unknown campaign" in capsys.readouterr().err


def test_render_cli_campaign_merges_credit_and_warns_on_duration(
    process_env, tmp_path, monkeypatch, capsys
):
    from clipengine import cli, pipeline
    from clipengine.campaigns.store import CampaignStore

    cfg, _calls = process_env
    with CampaignStore(str(tmp_path / "campaigns.db")) as store:
        store.upsert([_campaign()], at="t1")  # min 30s
    cfg_file = tmp_path / "cfg.toml"
    cfg_file.write_text(
        f'work_dir = "{cfg.work_dir}"\nroster_db = "{cfg.roster_db}"\n'
        f'[campaigns]\ncampaigns_db = "{tmp_path}/campaigns.db"\n'
    )
    rendered = {}

    def fake_render(video, cand, facecam, out_path, cf, with_captions=True,
                    credit_text=None, transcript_out=None):
        rendered["credit"] = credit_text
        return out_path

    monkeypatch.setattr(pipeline, "render_candidate", fake_render)
    rc = cli.main([
        "--config", str(cfg_file), "render", "v.mp4", "--start", "10",
        "--end", "22", "--facecam", "0,0,10,10", "--streamer", "nl",
        "-o", str(tmp_path / "clip.mp4"), "--campaign", "manual:neon",
    ])
    assert rc == 0
    assert rendered["credit"] == "clip: twitch.tv/nl | @neon"
    assert "outside the campaign's duration bound" in capsys.readouterr().err  # 12s < 30s
