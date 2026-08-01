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
    assert "100\\%" in g and "don'\\''t" in g


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


# -- snap-to-speech --------------------------------------------------------


def _speech():
    """Sentences at 2-6s, 8-14s, 20-27s, 30-38s with silence between."""
    return Transcript(segments=[
        TranscriptSegment(start=2.0, end=6.0, text="First sentence.", words=[]),
        TranscriptSegment(start=8.0, end=14.0, text="Second, longer sentence.", words=[]),
        TranscriptSegment(start=20.0, end=27.0, text="Third sentence.", words=[]),
        TranscriptSegment(start=30.0, end=38.0, text="Fourth sentence.", words=[]),
    ])


def test_snap_start_backs_up_to_sentence_start():
    start, end = pipeline.snap_to_speech(_speech(), 10.0, 27.0)
    assert start == pytest.approx(7.8)   # 8.0 - pad: sentence two from the top
    assert end == pytest.approx(27.2)    # already a boundary + pad


def test_snap_start_jumps_forward_when_backup_too_far():
    # 13.0 is 5s into sentence two (> max_shift 4) -> next sentence start
    start, _end = pipeline.snap_to_speech(_speech(), 13.0, 27.0)
    assert start == pytest.approx(19.8)  # 20.0 - pad


def test_snap_end_extends_to_finish_sentence():
    _start, end = pipeline.snap_to_speech(_speech(), 2.0, 25.0)
    assert end == pytest.approx(27.2)    # sentence three allowed to finish


def test_snap_end_retreats_when_extension_too_far():
    # 31.0 is 7s before sentence four ends (> max_shift) -> cut before it starts
    _start, end = pipeline.snap_to_speech(_speech(), 2.0, 31.0)
    assert end == pytest.approx(30.2)    # 30.0 + pad


def test_snap_leaves_silence_boundaries_alone():
    start, end = pipeline.snap_to_speech(_speech(), 7.0, 28.5)
    assert start == pytest.approx(6.8) and end == pytest.approx(28.7)  # pad only


def test_source_transcript_uses_cache(cfg, tmp_path, monkeypatch):
    import json

    src = tmp_path / "master.mov"
    src.write_text("video")
    cache = tmp_path / "master.mov.transcript.json"
    cache.write_text(json.dumps({"segments": [
        {"start": 1.0, "end": 3.0, "text": "cached", "words": []}
    ]}))
    monkeypatch.setattr(
        pipeline.transcribe, "transcribe",
        lambda wav: (_ for _ in ()).throw(AssertionError("must not re-transcribe")),
    )
    t = pipeline.source_transcript(str(src), cfg)
    assert t.segments[0].text == "cached"


def test_cli_snap_adjusts_window(cfg, fakes, tmp_path, monkeypatch, capsys):
    from clipengine import cli

    cfg_file = tmp_path / "cfg.toml"
    cfg_file.write_text(f'work_dir = "{cfg.work_dir}"\n')
    monkeypatch.setattr(pipeline, "source_transcript", lambda v, c: _speech())
    rc = cli.main([
        "--config", str(cfg_file), "repurpose", "asset.mp4",
        "-o", str(tmp_path / "out.mp4"), "--no-captions", "--snap",
        "--start", "10", "--end", "25",
    ])
    assert rc == 0
    assert "snapped window 10-25s -> 7.8-27.2s" in capsys.readouterr().err
    assert fakes["trim"] == (7.8, pytest.approx(19.4))  # snapped start/duration


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
