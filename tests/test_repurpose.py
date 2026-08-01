import pytest

from clipengine import pipeline
from clipengine.config import Config, EditConfig
from clipengine.edit.ffmpeg import vertical_fit_graph
from clipengine.models import SourceVideo, Transcript, TranscriptSegment


def _source(w=1920, h=1080):
    return SourceVideo(path="a.mp4", width=w, height=h, duration=20.0)


# -- filtergraph -----------------------------------------------------------


def test_fit_graph_blur_pad_layout():
    g = vertical_fit_graph(_source(), EditConfig())
    assert "force_original_aspect_ratio=increase" in g  # bg fills
    assert "boxblur" in g
    assert "force_original_aspect_ratio=decrease" in g  # fg fits
    assert "overlay=(W-w)/2:(H-h)/2" in g
    assert "drawtext" not in g


def test_fit_graph_credit_and_cta():
    g = vertical_fit_graph(_source(), EditConfig(), credit_text="via @forge",
                           cta_text="link in bio")
    assert "via @forge" in g and "y=60" in g       # credit at the top edge
    assert "link in bio" in g and "y=h-380" in g   # CTA above caption zone


def test_fit_graph_escapes_drawtext():
    g = vertical_fit_graph(_source(), EditConfig(), cta_text="100%: don't")
    assert "100\\%" in g and "don\\'t" in g


# -- pipeline --------------------------------------------------------------


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.work_dir = str(tmp_path / "work")
    return c


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    calls = {}

    def touch(path):
        open(path, "w").write("clip")
        return path

    monkeypatch.setattr(pipeline.edit, "probe", lambda p: _source())
    monkeypatch.setattr(
        pipeline.edit, "trim",
        lambda src, dst, s, d, c: calls.setdefault("trim", (s, d)) and touch(dst) or touch(dst),
    )

    def fake_fit(src, dst, source, c, credit_text=None, cta_text=None):
        calls["fit"] = {"credit": credit_text, "cta": cta_text}
        return touch(dst)

    monkeypatch.setattr(pipeline.edit, "vertical_fit", fake_fit)
    monkeypatch.setattr(pipeline.audio, "extract_wav", lambda v, w: w)
    monkeypatch.setattr(
        pipeline.transcribe, "transcribe", lambda wav: Transcript(segments=[])
    )
    monkeypatch.setattr(
        pipeline.edit, "burn_hook",
        lambda src, dst, hook, c: calls.setdefault("hook", hook) and touch(dst) or touch(dst),
    )
    return calls


def test_repurpose_no_speech_skips_captions(cfg, fakes, tmp_path):
    out = pipeline.repurpose_asset(
        "asset.mp4", str(tmp_path / "out.mp4"), cfg,
        hook="POV: you code 10x faster", cta="link in bio", credit_text="@forge",
    )
    assert out == str(tmp_path / "out.mp4")
    assert fakes["fit"] == {"credit": "@forge", "cta": "link in bio"}
    assert fakes["hook"] == "POV: you code 10x faster"


def test_repurpose_trim_window(cfg, fakes, tmp_path):
    pipeline.repurpose_asset(
        "asset.mp4", str(tmp_path / "out.mp4"), cfg, start=3.0, end=15.0,
        with_captions=False,
    )
    assert fakes["trim"] == (3.0, 12.0)


def test_repurpose_no_hook_moves_stage_to_output(cfg, fakes, tmp_path):
    out = pipeline.repurpose_asset(
        "asset.mp4", str(tmp_path / "out.mp4"), cfg, with_captions=False,
    )
    import os

    assert os.path.exists(out) and "hook" not in fakes


def test_repurpose_captions_burned_when_speech(cfg, fakes, monkeypatch, tmp_path):
    seg = TranscriptSegment(start=0.0, end=2.0, text="hello world", words=[])
    monkeypatch.setattr(
        pipeline.transcribe, "transcribe", lambda wav: Transcript(segments=[seg])
    )
    monkeypatch.setattr(
        pipeline.captions, "write_ass", lambda t, p, c: p
    )
    burned = {}

    def fake_burn(src, dst, ass, c):
        burned["ass"] = ass
        open(dst, "w").write("cap")
        return dst

    monkeypatch.setattr(pipeline.edit, "burn_subtitles", fake_burn)
    pipeline.repurpose_asset("asset.mp4", str(tmp_path / "out.mp4"), cfg)
    assert "ass" in burned


# -- CLI with campaign gate ------------------------------------------------


def test_cli_repurpose_campaign_caption_and_gate(cfg, fakes, tmp_path, capsys):
    from clipengine import cli
    from clipengine.campaigns.models import Campaign
    from clipengine.campaigns.store import CampaignStore

    cfg_file = tmp_path / "cfg.toml"
    cfg_file.write_text(
        f'work_dir = "{cfg.work_dir}"\n'
        f'[campaigns]\ncampaigns_db = "{tmp_path}/campaigns.db"\n'
    )
    with CampaignStore(str(tmp_path / "campaigns.db")) as store:
        store.upsert([Campaign(
            id="disc:forgegui", source="manual", title="ForgeGUI UGC",
            status="open", reward_model="cpm", reward_amount=3.0,
            budget_total=30000.0, budget_remaining=26677.0,
            rules_text="Must include #ForgeGUI. Post to TikTok. Vertical video only.",
        )], at="t1")
    rc = cli.main([
        "--config", str(cfg_file), "repurpose", "asset.mp4",
        "-o", str(tmp_path / "out.mp4"), "--no-captions",
        "--hook", "this AI builds Roblox GUIs",
        "--cta", "forgegui.com - link in bio",
        "--campaign", "disc:forgegui", "--platform", "tiktok",
    ])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "caption: #ForgeGUI" in out
    assert "gate: PASS" in out
