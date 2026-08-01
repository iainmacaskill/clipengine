import pytest

from clipengine.campaigns.gate import ClipFacts, preflight
from clipengine.campaigns.models import Campaign
from clipengine.campaigns.rules import parse_rules

RULES = """\
Post to TikTok or YouTube Shorts.
Must include #NeonClips and tag @neon in the caption.
Clips must be at least 30 seconds.
- No AI voiceovers
Source: https://twitch.tv/neon
"""


def _campaign(**over):
    base = dict(
        id="manual:neon", source="manual", title="Neon clips", status="open",
        reward_model="cpm", reward_amount=2.0, budget_total=5000.0,
        budget_remaining=4000.0, rules_text=RULES,
    )
    base.update(over)
    return Campaign(**base)


def _facts(**over):
    base = dict(
        duration_s=45.0,
        caption="insane clutch #NeonClips @neon #fyp",
        platform="tiktok",
        source_url="https://www.twitch.tv/neon/",
    )
    base.update(over)
    return ClipFacts(**base)


def _run(facts=None, campaign=None):
    campaign = campaign or _campaign()
    return preflight(facts or _facts(), parse_rules(campaign.rules_text), campaign)


def test_compliant_clip_passes():
    report = _run()
    assert report.passed
    assert not report.failures
    names = {r.name for r in report.results if r.status == "pass"}
    assert {"campaign", "duration", "hashtag", "mention", "platform", "source"} <= names


def test_missing_hashtag_fails():
    report = _run(_facts(caption="insane clutch @neon"))
    assert not report.passed
    assert any(r.name == "hashtag" and "#NeonClips" in r.detail for r in report.failures)


def test_mention_satisfied_by_burned_credit():
    report = _run(_facts(caption="insane clutch #NeonClips",
                         credit_text="clip: @neon"))
    assert not any(r.name == "mention" and r.status == "fail" for r in report.results)


def test_too_short_fails():
    report = _run(_facts(duration_s=12.0))
    assert any(r.name == "duration" and r.status == "fail" for r in report.results)


def test_max_duration_enforced():
    campaign = _campaign(rules_text="keep clips under 60 seconds")
    assert not _run(_facts(duration_s=90.0), campaign).passed
    assert _run(_facts(duration_s=45.0), campaign).passed


def test_wrong_platform_fails():
    report = _run(_facts(platform="instagram"))
    assert any(r.name == "platform" and r.status == "fail" for r in report.results)


def test_unknown_platform_skips_check():
    report = _run(_facts(platform=""))
    assert not any(r.name == "platform" for r in report.results)


def test_closed_campaign_fails():
    assert not _run(campaign=_campaign(status="completed")).passed


def test_exhausted_budget_fails():
    report = _run(campaign=_campaign(budget_remaining=0.0))
    assert any(r.name == "campaign" and "exhausted" in r.detail for r in report.failures)


def test_unknown_source_is_manual_not_fail():
    report = _run(_facts(source_url=""))
    assert report.passed  # manual items don't block
    assert any(r.name == "source" and r.status == "manual" for r in report.results)


def test_source_match_ignores_scheme_and_www():
    report = _run(_facts(source_url="http://www.twitch.tv/neon"))
    assert any(r.name == "source" and r.status == "pass" for r in report.results)


def test_banned_lines_surface_as_manual():
    report = _run()
    assert any(
        r.name == "banned" and "AI voiceovers" in r.detail for r in report.manual
    )


def test_unstructured_required_line_is_manual():
    campaign = _campaign(rules_text="Clips must show the brand logo clearly")
    report = _run(campaign=campaign)
    assert any(r.name == "required" and "brand logo" in r.detail for r in report.manual)


def test_no_rules_no_campaign_passes_empty():
    report = preflight(ClipFacts(duration_s=10.0), parse_rules(""))
    assert report.passed and report.results == []


# -- CLI wiring ------------------------------------------------------------


@pytest.fixture
def env(tmp_path, monkeypatch):
    from clipengine import cli
    from clipengine.campaigns.store import CampaignStore
    from clipengine.models import SourceVideo

    cfg = tmp_path / "cfg.toml"
    cfg.write_text(f'[campaigns]\ncampaigns_db = "{tmp_path / "campaigns.db"}"\n')
    with CampaignStore(str(tmp_path / "campaigns.db")) as store:
        store.upsert([_campaign()], at="t1")
    monkeypatch.setattr(
        "clipengine.edit.ffmpeg.probe",
        lambda p: SourceVideo(path=p, width=1080, height=1920, duration=45.0),
    )
    return str(cfg)


def _cli(env, *argv):
    from clipengine import cli

    return cli.main(["--config", env, *argv])


def test_cli_check_pass_and_fail(env, capsys):
    rc = _cli(env, "campaigns", "check", "clip.mp4", "--campaign", "manual:neon",
              "--caption", "clutch #NeonClips @neon", "--platform", "tiktok")
    assert rc == 0
    assert "PASS" in capsys.readouterr().out

    rc = _cli(env, "campaigns", "check", "clip.mp4", "--campaign", "manual:neon",
              "--caption", "no tags here", "--platform", "tiktok")
    assert rc == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.out
    assert "#NeonClips missing" in captured.err


def test_cli_check_unknown_campaign(env, capsys):
    rc = _cli(env, "campaigns", "check", "clip.mp4", "--campaign", "nope")
    assert rc == 1
    assert "unknown campaign" in capsys.readouterr().err


def test_publish_refused_by_gate(env, capsys):
    rc = _cli(env, "publish", "tiktok", "clip.mp4",
              "--title", "missing everything", "--campaign", "manual:neon")
    assert rc == 3
    assert "compliance gate failed" in capsys.readouterr().err


def test_queue_add_refused_by_gate(env, tmp_path, capsys):
    with open(tmp_path / "cfg.toml", "a") as f:
        f.write(f'[schedule]\nqueue_db = "{tmp_path / "queue.db"}"\n')
    rc = _cli(env, "queue", "add", "tiktok", "clip.mp4", "--account", "acct",
              "--title", "missing everything", "--campaign", "manual:neon")
    assert rc == 3
    assert "queue refused" in capsys.readouterr().err


def test_queue_add_passes_gate_and_queues(env, tmp_path, capsys):
    with open(tmp_path / "cfg.toml", "a") as f:
        f.write(f'[schedule]\nqueue_db = "{tmp_path / "queue.db"}"\n')
    rc = _cli(env, "queue", "add", "tiktok", "clip.mp4", "--account", "acct",
              "--title", "clutch #NeonClips @neon", "--campaign", "manual:neon")
    assert rc == 0
    assert "scheduled" in capsys.readouterr().out
