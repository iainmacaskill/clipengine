import wave

import numpy as np
import pytest

from clipengine.package.music import MusicSegment, check, flag_segments, music_scores

SR = 16000


def _write(path, x):
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((x * 32767).astype(np.int16).tobytes())


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _music(dur=12.0, seed=1):
    """Sustained chords + a 120 BPM beat."""
    rng = np.random.default_rng(seed)
    x = np.zeros(int(dur * SR))
    chords = [(220, 277, 330), (196, 247, 294), (174, 220, 262), (147, 196, 247)]
    for i in range(int(dur / 2)):
        seg = _t(2.0)
        chord = chords[i % len(chords)]
        y = sum(0.2 * np.sin(2 * np.pi * f * seg) + 0.1 * np.sin(2 * np.pi * 2 * f * seg) for f in chord)
        x[int(i * 2 * SR) : int(i * 2 * SR) + len(seg)] += y
    for b in np.arange(0, dur, 0.5):
        i0, n = int(b * SR), int(0.05 * SR)
        if i0 + n < len(x):
            x[i0 : i0 + n] += 0.5 * rng.normal(0, 1, n) * np.exp(-np.linspace(0, 8, n))
    return 0.5 * x


def _speech(dur=12.0, seed=1):
    """Speech-like: short harmonic bursts, shifting pitch, syllabic gaps."""
    rng = np.random.default_rng(seed)
    x = np.zeros(int(dur * SR))
    pos = 0.0
    while pos < dur - 0.4:
        syl = rng.uniform(0.08, 0.25)
        f0 = rng.uniform(90, 220)
        seg = _t(syl)
        y = sum(
            0.25 / k * np.sin(2 * np.pi * k * f0 * seg * (1 + 0.02 * np.sin(2 * np.pi * 3 * seg)))
            for k in range(1, 6)
        )
        i0 = int(pos * SR)
        x[i0 : i0 + len(seg)] += y * np.hanning(len(seg))
        pos += syl + rng.uniform(0.02, 0.15)
        if rng.random() < 0.15:
            pos += rng.uniform(0.2, 0.5)
    return x


def test_music_scores_high(tmp_path):
    p = tmp_path / "m.wav"
    _write(p, _music())
    assert music_scores(str(p)).mean() > 0.45


def test_speech_scores_low(tmp_path):
    p = tmp_path / "s.wav"
    _write(p, _speech())
    assert music_scores(str(p)).max() < 0.30


def test_noise_scores_low(tmp_path):
    p = tmp_path / "n.wav"
    _write(p, 0.2 * np.random.default_rng(0).normal(0, 1, 12 * SR))
    assert music_scores(str(p)).max() < 0.30


def test_mixed_flags_music_bed_section(tmp_path):
    speech, music = _speech(10.0), _music(10.0)
    mixed = np.concatenate([speech, speech + 0.7 * music, speech])
    p = tmp_path / "mix.wav"
    _write(p, mixed)
    segments = check(str(p))
    assert len(segments) == 1
    seg = segments[0]
    # music truly spans 10-20s; flagging may be a little wide (deliberate) but
    # must cover the bed and not swallow the clean speech
    assert seg.start <= 10.5 and seg.end >= 19.0
    assert seg.start >= 6.0 and seg.end <= 24.0


def test_clean_speech_yields_no_segments(tmp_path):
    p = tmp_path / "s.wav"
    _write(p, _speech(20.0))
    assert check(str(p)) == []


def test_flag_segments_merging_and_min_duration():
    scores = np.zeros(30)
    scores[5:9] = 0.5    # 4s block
    scores[10:14] = 0.5  # merges across the 1s gap
    scores[20:21] = 0.9  # 1s blip: below min duration, dropped
    segs = flag_segments(scores, threshold=0.3)
    assert len(segs) == 1
    assert segs[0].start <= 5.0 and 13.0 <= segs[0].end <= 15.0


def test_flag_segments_empty():
    assert flag_segments(np.zeros(10)) == []


def test_mute_segments_requires_segments(tmp_path):
    from clipengine.package.music import mute_segments

    with pytest.raises(ValueError):
        mute_segments("in.mp4", "out.mp4", [])


def test_segment_dataclass_fields():
    s = MusicSegment(1.0, 4.0, 0.5)
    assert s.end - s.start == 3.0
