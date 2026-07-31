from clipengine.config import DetectConfig
from clipengine.detect.fusion import fuse
from clipengine.models import SignalSeries


def _cfg(**kw):
    cfg = DetectConfig(target_duration=10.0, min_gap=5.0, top_n=3, pre_roll=2.0)
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def test_picks_window_at_signal_spike():
    scores = [0.0] * 120
    for i in range(60, 70):
        scores[i] = 10.0
    series = [SignalSeries("chat_velocity", scores)]
    picked = fuse(series, {"chat_velocity": 1.0}, duration=119.0, cfg=_cfg())
    assert picked, "expected at least one candidate"
    top = picked[0]
    assert top.start <= 60 <= top.end, f"spike not inside window {top.start}-{top.end}"


def test_candidates_do_not_overlap():
    scores = [0.0] * 300
    for peak in (50, 150, 250):
        for i in range(peak, peak + 10):
            scores[i] = 5.0
    series = [SignalSeries("audio_energy", scores)]
    picked = fuse(series, {"audio_energy": 1.0}, duration=299.0, cfg=_cfg())
    assert len(picked) >= 2
    ordered = sorted(picked, key=lambda c: c.start)
    for a, b in zip(ordered, ordered[1:]):
        assert a.end <= b.start, "candidate windows overlap"


def test_flat_signal_yields_no_crash_and_bounded_windows():
    series = [SignalSeries("chat_velocity", [1.0] * 100)]
    picked = fuse(series, {"chat_velocity": 1.0}, duration=99.0, cfg=_cfg())
    for c in picked:
        assert 0 <= c.start < c.end <= 99.0


def test_weights_shift_ranking():
    a = [0.0] * 100
    b = [0.0] * 100
    for i in range(20, 28):
        a[i] = 5.0
    for i in range(70, 78):
        b[i] = 5.0
    series = [SignalSeries("chat_velocity", a), SignalSeries("audio_energy", b)]
    picked = fuse(
        series, {"chat_velocity": 10.0, "audio_energy": 0.1}, duration=99.0, cfg=_cfg()
    )
    top = picked[0]
    assert top.start <= 20 <= top.end, "heavily-weighted chat spike should rank first"
