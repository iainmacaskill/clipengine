import json

import numpy as np
import pytest

from clipengine.detect.gamecv import (
    EventTemplate,
    GameProfile,
    load_profile,
    ncc_max,
    score_frames,
)


def _template(seed=1, h=20, w=40):
    rng = np.random.default_rng(seed)
    return rng.uniform(0, 255, size=(h, w))


def _frame(h=180, w=320, seed=0):
    rng = np.random.default_rng(seed)
    return rng.uniform(0, 255, size=(h, w))


# -- ncc_max ---------------------------------------------------------------


def test_ncc_exact_match_scores_near_one():
    template = _template()
    region = _frame(80, 120, seed=9)
    region[30:50, 40:80] = template  # paste at an offset
    assert ncc_max(region, template) > 0.99


def test_ncc_no_match_scores_low():
    assert ncc_max(_frame(80, 120, seed=2), _template(seed=3)) < 0.5


def test_ncc_brightness_invariant():
    """NCC must survive stream-side brightness/contrast shifts."""
    template = _template()
    region = _frame(80, 120, seed=9)
    region[30:50, 40:80] = template * 0.6 + 40  # dimmed + offset
    assert ncc_max(region, template) > 0.99


def test_ncc_template_larger_than_region():
    assert ncc_max(_template(h=10, w=10), _template(h=50, w=50)) == -1.0


def test_ncc_flat_template_rejected():
    assert ncc_max(_frame(80, 120), np.full((20, 40), 128.0)) == -1.0


# -- score_frames ----------------------------------------------------------


def _profile_with(template, threshold=0.8, min_gap_s=30.0):
    return GameProfile(
        game="test", capture_width=320,
        events=[EventTemplate(
            name="victory", template=template,
            region=(0.25, 0.25, 0.5, 0.5), threshold=threshold, min_gap_s=min_gap_s,
        )],
    )


def _frames_with_event(event_seconds, n_seconds=120, template=None):
    """1 fps frames of noise; template pasted into the region at given seconds."""
    frames = []
    for t in range(n_seconds):
        f = _frame(seed=1000 + t)
        if t in event_seconds and template is not None:
            # region is x 80..240, y 45..135 in a 320x180 frame
            f[60 : 60 + template.shape[0], 100 : 100 + template.shape[1]] = template
        frames.append(f)
    return frames


def test_hits_at_event_times_and_series_spikes():
    template = _template()
    frames = _frames_with_event({40, 90}, template=template)
    series, hits = score_frames(iter(frames), _profile_with(template), fps=1.0, duration=119)
    assert [(h.name, int(h.at)) for h in hits] == [("victory", 40), ("victory", 90)]
    assert series.name == "game_events"
    assert series.scores[40] > 0.9 and series.scores[90] > 0.9
    assert max(series.scores[0:35]) < 0.8  # noise seconds stay low


def test_min_gap_dedupes_consecutive_hits():
    template = _template()
    # event visible for 5 consecutive seconds (banner on screen)
    frames = _frames_with_event({50, 51, 52, 53, 54}, template=template)
    _series, hits = score_frames(
        iter(frames), _profile_with(template, min_gap_s=30), fps=1.0, duration=119
    )
    assert len(hits) == 1 and int(hits[0].at) == 50


def test_threshold_filters_weak_matches():
    template = _template()
    frames = _frames_with_event(set(), n_seconds=30)  # pure noise
    _series, hits = score_frames(
        iter(frames), _profile_with(template, threshold=0.8), fps=1.0, duration=29
    )
    assert hits == []


# -- profile loading -------------------------------------------------------


def _write_png(path, array):
    """Write a grayscale array as PNG via ffmpeg (same decode path as prod)."""
    import subprocess

    h, w = array.shape
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "gray",
         "-s", f"{w}x{h}", "-i", "-", str(path)],
        input=array.astype(np.uint8).tobytes(), check=True,
    )


def test_load_profile_roundtrip(tmp_path):
    template = _template().astype(np.uint8).astype(np.float64)
    _write_png(tmp_path / "victory.png", template)
    (tmp_path / "manifest.json").write_text(json.dumps({
        "game": "testgame", "capture_width": 640,
        "events": [{"name": "victory", "template": "victory.png",
                    "region": [0.3, 0.3, 0.4, 0.3], "threshold": 0.75}],
    }))
    profile = load_profile(str(tmp_path))
    assert profile.game == "testgame" and profile.capture_width == 640
    ev = profile.events[0]
    assert ev.name == "victory" and ev.threshold == 0.75
    assert np.array_equal(ev.template, template)  # png decode is lossless


def test_load_profile_missing_template(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({
        "events": [{"name": "x", "template": "nope.png", "region": [0, 0, 1, 1]}],
    }))
    with pytest.raises(FileNotFoundError):
        load_profile(str(tmp_path))


def test_load_profile_bad_region(tmp_path):
    _write_png(tmp_path / "t.png", _template())
    (tmp_path / "manifest.json").write_text(json.dumps({
        "events": [{"name": "x", "template": "t.png", "region": [0, 0, 500, 200]}],
    }))
    with pytest.raises(ValueError, match="fractional"):
        load_profile(str(tmp_path))


def test_load_profile_no_events(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"events": []}))
    with pytest.raises(ValueError, match="no events"):
        load_profile(str(tmp_path))


# -- pipeline integration --------------------------------------------------


def test_compute_series_includes_game_events(tmp_path, monkeypatch):
    from clipengine import pipeline
    from clipengine.config import Config
    from clipengine.models import SignalSeries, SourceVideo

    cfg = Config()
    cfg.work_dir = str(tmp_path)
    cfg.detect.game_profile = str(tmp_path / "profile")
    cfg.detect.weight_game_events = 2.0

    monkeypatch.setattr(
        pipeline.edit, "probe",
        lambda p: SourceVideo(path=p, width=1920, height=1080, duration=100.0),
    )
    monkeypatch.setattr(pipeline.audio, "extract_wav", lambda v, w: w)
    monkeypatch.setattr(
        pipeline.audio, "energy_series", lambda w: SignalSeries("audio_energy", [0.0] * 100)
    )
    monkeypatch.setattr(
        "clipengine.detect.gamecv.detect_events",
        lambda video, profile, duration: (
            SignalSeries("game_events", [0.0] * 100), []
        ),
    )
    series, weights, duration = pipeline.compute_series("v.mp4", None, cfg)
    assert {s.name for s in series} == {"audio_energy", "game_events"}
    assert weights["game_events"] == 2.0
