import pytest

from clipengine import pipeline
from clipengine.config import Config, EditConfig
from clipengine.edit.ffmpeg import vertical_fit_graph
from clipengine.models import SourceVideo, Transcript, TranscriptSegment


def _source(w=1920, h=1080):
    return SourceVideo(path="a.mp4", width=w, height=h, duration=20.0)


# -- filtergraph -----------------------------------------------------------


def test_fit_graph_blur_pad_layout():
    g = vertical_fit_graph(EditConfig())
    assert "force_original_aspect_ratio=increase" in g  # bg fills
    assert "boxblur" in g
    assert "force_original_aspect_ratio=decrease" in g  # fg fits
    assert "overlay=(W-w)/2:(H-h)/2" in g
    assert "drawtext" not in g


def test_fit_graph_credit_and_cta():
    g = vertical_fit_graph(EditConfig(), credit_text="via @forge",
                           cta_text="link in bio")
    assert "via @forge" in g and "y=60" in g       # credit at the top edge
    assert "link in bio" in g and "y=h-380" in g   # CTA above caption zone


def test_fit_graph_escapes_drawtext():
    g = vertical_fit_graph(EditConfig(), cta_text="100%: don't")
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

    monkeypatch.setattr(pipeline.edit, "probe", lambda p: _source())

    def fake_render(src, dst, c, **kw):
        calls["render"] = {"src": src, **kw}
        open(dst, "w").write("clip")
        return dst

    monkeypatch.setattr(pipeline.edit, "render_repurpose", fake_render)
    monkeypatch.setattr(
        pipeline.audio, "extract_wav",
        lambda v, w, start=None, duration=None: w,
    )
    monkeypatch.setattr(
        pipeline.transcribe, "transcribe", lambda wav: Transcript(segments=[])
    )
    # these tests cover the drawtext fallback; the text-card path has its own
    monkeypatch.setattr("clipengine.edit.textcard.available", lambda: False)
    return calls


def test_repurpose_textcard_path(cfg, fakes, tmp_path, monkeypatch):
    """With Pillow available, hook + CTA become styled cards in the one pass."""
    import clipengine.edit.textcard as tc

    monkeypatch.setattr("clipengine.edit.textcard.available", lambda: True)
    rendered = []

    def fake_card(text, out_png, width, style=None):
        rendered.append((text, width, getattr(style, "font_size", 76)))
        open(out_png, "w").write("png")
        return out_png, 120

    monkeypatch.setattr(tc, "render_text_card", fake_card)
    out = pipeline.repurpose_asset(
        "asset.mp4", str(tmp_path / "out.mp4"), cfg, with_captions=False,
        hook="new *series* alert 🚨", cta="link in bio",
    )
    assert out == str(tmp_path / "out.mp4")
    assert [t for t, _w, _s in rendered] == ["new *series* alert 🚨", "link in bio"]
    assert rendered[1][2] == 46                      # CTA renders smaller
    r = fakes["render"]
    assert [(y, sec) for _p, y, sec in r["cards"]] == [(0.12, None), (0.74, None)]
    # CTA and hook live in the card overlays, not drawtext
    assert r["cta_text"] is None and r["hook_text"] is None


def test_repurpose_no_speech_skips_captions(cfg, fakes, tmp_path):
    out = pipeline.repurpose_asset(
        "asset.mp4", str(tmp_path / "out.mp4"), cfg,
        hook="POV: you code 10x faster", cta="link in bio", credit_text="@forge",
    )
    assert out == str(tmp_path / "out.mp4")
    r = fakes["render"]
    assert r["credit_text"] == "@forge" and r["cta_text"] == "link in bio"
    assert r["hook_text"] == "POV: you code 10x faster"
    assert r["ass_path"] is None


def test_repurpose_trim_window(cfg, fakes, tmp_path):
    pipeline.repurpose_asset(
        "asset.mp4", str(tmp_path / "out.mp4"), cfg, start=3.0, end=15.0,
        with_captions=False,
    )
    assert fakes["render"]["start"] == 3.0
    assert fakes["render"]["duration"] == pytest.approx(12.0)


def test_repurpose_bare_renders_output(cfg, fakes, tmp_path):
    out = pipeline.repurpose_asset(
        "asset.mp4", str(tmp_path / "out.mp4"), cfg, with_captions=False,
    )
    import os

    assert os.path.exists(out) and fakes["render"]["hook_text"] is None


def test_repurpose_captions_burned_when_speech(cfg, fakes, monkeypatch, tmp_path):
    seg = TranscriptSegment(start=0.0, end=2.0, text="hello world", words=[])
    monkeypatch.setattr(
        pipeline.transcribe, "transcribe", lambda wav: Transcript(segments=[seg])
    )
    monkeypatch.setattr(
        pipeline.captions, "write_ass", lambda t, p, c: p
    )
    pipeline.repurpose_asset("asset.mp4", str(tmp_path / "out.mp4"), cfg)
    assert fakes["render"]["ass_path"]


def test_repurpose_uses_cached_source_transcript(cfg, fakes, tmp_path, monkeypatch):
    """A cached master transcript is sliced to the window - Whisper must not run."""
    import json

    src = tmp_path / "asset.mp4"
    src.write_text("video")
    (tmp_path / "asset.mp4.transcript.json").write_text(json.dumps({"segments": [
        {"start": 10.0, "end": 12.0, "text": "inside the window", "words": []},
        {"start": 40.0, "end": 42.0, "text": "outside", "words": []},
    ]}))
    monkeypatch.setattr(
        pipeline.transcribe, "transcribe",
        lambda wav: (_ for _ in ()).throw(AssertionError("must not re-transcribe")),
    )
    written = {}

    def fake_ass(t, p, c):
        written["transcript"] = t
        return p

    monkeypatch.setattr(pipeline.captions, "write_ass", fake_ass)
    pipeline.repurpose_asset(str(src), str(tmp_path / "out.mp4"), cfg,
                             start=9.0, end=14.0)
    segs = written["transcript"].segments
    assert [s.text for s in segs] == ["inside the window"]
    assert segs[0].start == pytest.approx(1.0)  # shifted clip-relative
    assert fakes["render"]["ass_path"]


# -- transcript slicing ----------------------------------------------------


def test_slice_transcript_shifts_and_filters():
    s = pipeline.slice_transcript(_speech(), 8.0, 27.0)
    assert [seg.text for seg in s.segments] == [
        "Second, longer sentence.", "Third sentence."
    ]
    assert s.segments[0].start == pytest.approx(0.0)
    assert s.segments[0].end == pytest.approx(6.0)
    assert s.segments[1].start == pytest.approx(12.0)


def test_slice_transcript_clamps_partial_overlap_and_words():
    from clipengine.models import Word

    t = Transcript(segments=[TranscriptSegment(
        start=5.0, end=9.0, text="four words in here",
        words=[Word(5.0, 6.0, "four"), Word(6.0, 7.0, "words"),
               Word(7.0, 8.0, "in"), Word(8.0, 9.0, "here")],
    )])
    s = pipeline.slice_transcript(t, 6.5, 8.5)
    seg = s.segments[0]
    assert seg.start == 0.0                      # clamped, not negative
    assert [w.text for w in seg.words] == ["words", "in", "here"]
    assert seg.words[0].start == 0.0


# -- single-pass renderer --------------------------------------------------


def test_render_repurpose_is_one_ffmpeg_call(monkeypatch):
    from clipengine.edit import ffmpeg as ff

    cmds = []
    monkeypatch.setattr(ff.subprocess, "run", lambda cmd, check: cmds.append(cmd))
    ff.render_repurpose(
        "in.mp4", "out.mp4", EditConfig(), credit_text="via @x",
        ass_path="work/captions.ass",
        cards=[("hook.png", 0.12, None), ("cta.png", 0.74, 3.0)],
        start=3.0, duration=12.0,
    )
    assert len(cmds) == 1
    cmd = cmds[0]
    i_src = cmd.index("-i")
    assert cmd[i_src - 4:i_src] == ["-ss", "3.000", "-t", "12.000"]  # demuxer trim
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "subtitles='work/captions.ass'" in graph
    assert "via @x" in graph
    assert "0.120*H" in graph and "0.740*H" in graph
    assert "enable='lt(t,3.0)'" in graph          # timed card
    assert cmd.count("-i") == 3                   # source + two card PNGs


def test_render_repurpose_hook_fallback_drawtext(monkeypatch):
    from clipengine.edit import ffmpeg as ff

    cmds = []
    monkeypatch.setattr(ff.subprocess, "run", lambda cmd, check: cmds.append(cmd))
    ff.render_repurpose("in.mp4", "out.mp4", EditConfig(),
                        hook_text="you're not ready")
    graph = cmds[0][cmds[0].index("-filter_complex") + 1]
    assert "you'\\''re not ready" in graph        # quote-break apostrophe
    assert "enable='lt(t,2.5)'" in graph          # hook shows over the open


def test_subtitles_filter_escapes_path():
    from clipengine.edit.ffmpeg import subtitles_filter

    assert subtitles_filter("work/captions.ass") == "subtitles='work/captions.ass'"
    assert subtitles_filter("C:/o'k.ass") == "subtitles='C\\:/o'\\''k.ass'"


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
    assert fakes["render"]["start"] == 7.8              # snapped start/duration
    assert fakes["render"]["duration"] == pytest.approx(19.4)


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
