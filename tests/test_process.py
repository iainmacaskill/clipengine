import json

import pytest

from clipengine import pipeline
from clipengine.config import Config
from clipengine.models import ClipCandidate, FacecamRegion
from clipengine.roster import PermissionError_, Roster


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.work_dir = str(tmp_path / "work")
    c.roster_db = str(tmp_path / "roster.db")
    return c


def _allow(cfg, streamer="nl", credit=""):
    with Roster(cfg.roster_db) as r:
        r.add(streamer, source="published_policy", evidence="https://x/policy", credit=credit)


def _candidates():
    return [
        ClipCandidate(start=100.0, end=175.0, score=3.0, signal_breakdown={"chat_velocity": 2.0}),
        ClipCandidate(start=300.0, end=375.0, score=2.0),
        ClipCandidate(start=500.0, end=575.0, score=1.0),
    ]


@pytest.fixture
def patched(monkeypatch, tmp_path, cfg):
    """Stub the heavy stages; record calls."""
    calls = {"rendered": [], "screened": []}
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(pipeline, "detect_candidates", lambda v, c, cf: _candidates())

    def fake_render(video, cand, facecam, out_path, cf, with_captions=True,
                    credit_text=None, transcript_out=None):
        calls["rendered"].append((cand.start, credit_text, out_path))
        open(out_path, "w").write("clip")
        return out_path

    monkeypatch.setattr(pipeline, "render_candidate", fake_render)
    monkeypatch.setattr(pipeline.audio, "extract_wav", lambda v, w: w)
    monkeypatch.setattr(
        "clipengine.package.music.check", lambda wav, threshold=0.3: calls.setdefault("music", [])
    )
    return calls


def test_process_requires_roster_permission(cfg, tmp_path):
    with pytest.raises(PermissionError_):
        pipeline.process_vod(
            "v.mp4", None, "unlisted", str(tmp_path / "out"), cfg,
            facecam=FacecamRegion(0, 0, 10, 10),
        )


def test_process_renders_top_n_with_credit(cfg, tmp_path, patched):
    _allow(cfg, "nl", credit="follow twitch.tv/nl")
    manifest = pipeline.process_vod(
        "v.mp4", None, "nl", str(tmp_path / "out"), cfg,
        top_n=2, facecam=FacecamRegion(0, 0, 10, 10),
    )
    assert len(manifest) == 2  # top_n respected
    assert all(m["status"] == "rendered" for m in manifest)
    assert all(m["credit"] == "follow twitch.tv/nl" for m in manifest)
    assert [c[1] for c in patched["rendered"]] == ["follow twitch.tv/nl"] * 2
    saved = json.load(open(tmp_path / "out" / "manifest.json"))
    assert saved == manifest


def test_process_default_credit_from_login(cfg, tmp_path, patched):
    _allow(cfg, "SomeStreamer", credit="")
    manifest = pipeline.process_vod(
        "v.mp4", None, "SomeStreamer", str(tmp_path / "out"), cfg,
        top_n=1, facecam=FacecamRegion(0, 0, 10, 10),
    )
    assert manifest[0]["credit"] == "clip: twitch.tv/somestreamer"


def test_process_isolates_per_clip_failure(cfg, tmp_path, patched, monkeypatch):
    _allow(cfg)

    def flaky_render(video, cand, facecam, out_path, cf, with_captions=True,
                     credit_text=None, transcript_out=None):
        if cand.start == 300.0:
            raise RuntimeError("ffmpeg exploded")
        open(out_path, "w").write("clip")
        return out_path

    monkeypatch.setattr(pipeline, "render_candidate", flaky_render)
    manifest = pipeline.process_vod(
        "v.mp4", None, "nl", str(tmp_path / "out"), cfg,
        top_n=3, facecam=FacecamRegion(0, 0, 10, 10),
    )
    statuses = [m["status"] for m in manifest]
    assert statuses == ["rendered", "failed", "rendered"]
    assert "ffmpeg exploded" in manifest[1]["error"]


def test_process_mutes_flagged_clips(cfg, tmp_path, patched, monkeypatch):
    from clipengine.package.music import MusicSegment

    _allow(cfg)
    monkeypatch.setattr(
        "clipengine.package.music.check",
        lambda wav, threshold=0.3: [MusicSegment(5.0, 12.0, 0.5)],
    )
    muted = []

    def fake_mute(src, dst, segments):
        muted.append(src)
        open(dst, "w").write("muted")
        return dst

    monkeypatch.setattr("clipengine.package.music.mute_segments", fake_mute)
    manifest = pipeline.process_vod(
        "v.mp4", None, "nl", str(tmp_path / "out"), cfg,
        top_n=1, facecam=FacecamRegion(0, 0, 10, 10),
    )
    assert manifest[0]["muted_segments"] == [{"start": 5.0, "end": 12.0}]
    assert len(muted) == 1
    assert open(manifest[0]["path"]).read() == "muted"  # muted file replaced original


def test_process_cli_queues_rendered_clips(cfg, tmp_path, patched, monkeypatch):
    _allow(cfg)
    cfg_file = tmp_path / "cfg.toml"
    cfg_file.write_text(
        f'work_dir = "{cfg.work_dir}"\nroster_db = "{cfg.roster_db}"\n'
        f'[schedule]\nqueue_db = "{tmp_path}/q.db"\n'
        f'windows = ["00:00-23:45"]\nmin_spacing_hours = 0.5\ndaily_cap = 10\n'
    )
    from clipengine import cli

    rc = cli.main(
        [
            "--config", str(cfg_file), "process", "v.mp4", "--streamer", "nl",
            "-o", str(tmp_path / "out"), "--top", "2", "--facecam", "0,0,10,10",
            "--queue-platform", "youtube", "--account", "chan1",
            "--title-template", "{streamer} highlight {i}",
        ]
    )
    assert rc == 0
    from clipengine.publish.scheduler import Queue

    with Queue(str(tmp_path / "q.db")) as q:
        posts = q.list()
    assert len(posts) == 2
    assert posts[0].title == "nl highlight 1"
    assert posts[0].account == "chan1"
