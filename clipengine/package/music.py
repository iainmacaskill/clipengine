"""Music detection for DMCA screening.

Background music inside stream audio is the #1 takedown/claim cause for clips
(product plan §9). This module is the local screening layer: a numpy DSP
heuristic that flags "music-likely" time segments so they can be muted, replaced,
or sent for review. It deliberately errs toward flagging.

It does NOT identify tracks. Definitive "is this copyrighted, and what is it?"
requires an audio fingerprinting provider (AudD / ACRCloud / etc.) - see
``identify_segments`` for the integration point. Screen locally first: at
pennies per lookup, fingerprinting only the flagged segments is what keeps the
per-clip cost model intact.

Features, per one-second block over an STFT:
- tonal stability (+): sustained spectral peaks across frames (notes/chords)
- rhythmic periodicity (+): onset-flux autocorrelation peaking in 60-180 BPM lags
- syllabic modulation (-): 3-8 Hz energy-envelope modulation typical of speech
"""
from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass

import numpy as np

_N_FFT = 2048
_HOP = 512
_PEAK_K = 8            # spectral peaks tracked per frame
_BAND = (100.0, 4000.0)  # Hz band for peak tracking
_TEMPO_LAGS = (0.33, 1.0)  # seconds: 60-180 BPM
_CONTEXT_S = 4.0       # window for rhythm/modulation features
_W_STABILITY = 0.5
_W_RHYTHM = 0.5
_W_MODULATION = 0.6
_THRESHOLD = 0.30      # per-second music score threshold
_MIN_SEGMENT_S = 3.0   # ignore blips shorter than this
_MERGE_GAP_S = 1.5     # merge flagged seconds separated by gaps up to this
_PAD_S = 0.5           # widen reported segments by this much each side


@dataclass
class MusicSegment:
    start: float
    end: float
    score: float


def _read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as wf:
        rate = wf.getframerate()
        assert wf.getnchannels() == 1, "expected mono wav (use detect.audio.extract_wav)"
        raw = wf.readframes(wf.getnframes())
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    return x, rate


def _stft_mag(x: np.ndarray) -> np.ndarray:
    if len(x) < _N_FFT:
        return np.zeros((0, _N_FFT // 2 + 1))
    n_frames = 1 + (len(x) - _N_FFT) // _HOP
    idx = np.arange(_N_FFT)[None, :] + _HOP * np.arange(n_frames)[:, None]
    frames = x[idx] * np.hanning(_N_FFT)
    return np.abs(np.fft.rfft(frames, axis=1))


def _peak_bins(mag: np.ndarray, rate: int) -> list[np.ndarray]:
    """Top-K spectral peak bins per frame, within the tracking band."""
    freqs = np.fft.rfftfreq(_N_FFT, 1 / rate)
    lo = int(np.searchsorted(freqs, _BAND[0]))
    hi = int(np.searchsorted(freqs, _BAND[1]))
    band = mag[:, lo:hi]
    out = []
    for row in band:
        if row.max() <= 0:
            out.append(np.array([], dtype=int))
            continue
        k = min(_PEAK_K, row.size)
        peaks = np.argpartition(row, -k)[-k:]
        # keep only meaningful peaks (above 10% of the frame max)
        out.append(np.sort(peaks[row[peaks] > 0.1 * row.max()]) + lo)
    return out


def _stability_per_frame(peaks: list[np.ndarray]) -> np.ndarray:
    """Fraction of a frame's peaks persisting into the next frame (±1 bin)."""
    n = len(peaks)
    stab = np.zeros(n)
    for i in range(n - 1):
        a, b = peaks[i], peaks[i + 1]
        if len(a) == 0 or len(b) == 0:
            continue
        matches = sum(1 for p in a if np.any(np.abs(b - p) <= 1))
        stab[i] = matches / len(a)
    if n > 1:
        stab[-1] = stab[-2]
    return stab


def music_scores(wav_path: str) -> np.ndarray:
    """Per-second music-likelihood scores (arbitrary units around _THRESHOLD)."""
    x, rate = _read_wav(wav_path)
    mag = _stft_mag(x)
    if mag.shape[0] < 4:
        return np.zeros(max(1, int(len(x) / rate)))
    fps = rate / _HOP  # STFT frames per second

    stab = _stability_per_frame(_peak_bins(mag, rate))
    energy = mag.sum(axis=1)
    flux = np.maximum(np.diff(mag, axis=0), 0).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    if flux.std() > 0:
        flux = (flux - flux.mean()) / flux.std()

    n_seconds = int(len(x) / rate)
    half_ctx = int(_CONTEXT_S * fps / 2)
    lag_lo, lag_hi = int(_TEMPO_LAGS[0] * fps), int(_TEMPO_LAGS[1] * fps)
    scores = np.zeros(max(n_seconds, 1))

    for s in range(len(scores)):
        centre = int((s + 0.5) * fps)
        a = max(0, centre - half_ctx)
        b = min(len(flux), centre + half_ctx)
        f0, f1 = int(s * fps), min(int((s + 1) * fps), len(stab))

        stability = float(stab[f0:f1].mean()) if f1 > f0 else 0.0

        rhythm = 0.0
        ctx_flux = flux[a:b] - flux[a:b].mean()
        if len(ctx_flux) > lag_hi and ctx_flux.std() > 0:
            ac = np.correlate(ctx_flux, ctx_flux, mode="full")[len(ctx_flux) - 1 :]
            if ac[0] > 0:
                rhythm = float(np.max(ac[lag_lo : lag_hi + 1]) / ac[0])

        modulation = 0.0
        env = energy[a:b]
        if len(env) > 8 and env.sum() > 0:
            env = env - env.mean()
            spec = np.abs(np.fft.rfft(env))
            mod_freqs = np.fft.rfftfreq(len(env), 1 / fps)
            band = (mod_freqs >= 3.0) & (mod_freqs <= 8.0)
            total = spec[1:].sum()  # skip DC
            if total > 0:
                modulation = float(spec[band].sum() / total)

        scores[s] = (
            _W_STABILITY * stability + _W_RHYTHM * rhythm - _W_MODULATION * modulation
        )
    return scores


def flag_segments(scores: np.ndarray, threshold: float = _THRESHOLD) -> list[MusicSegment]:
    """Threshold per-second scores into merged, padded music segments."""
    flagged = scores >= threshold
    segments: list[MusicSegment] = []
    start = None
    for i, on in enumerate(list(flagged) + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            segments.append(
                MusicSegment(float(start), float(i), float(scores[start:i].mean()))
            )
            start = None
    # merge across small gaps
    merged: list[MusicSegment] = []
    for seg in segments:
        if merged and seg.start - merged[-1].end <= _MERGE_GAP_S:
            prev = merged[-1]
            merged[-1] = MusicSegment(
                prev.start, seg.end, max(prev.score, seg.score)
            )
        else:
            merged.append(seg)
    out = []
    for seg in merged:
        if seg.end - seg.start >= _MIN_SEGMENT_S:
            out.append(
                MusicSegment(max(0.0, seg.start - _PAD_S), seg.end + _PAD_S, seg.score)
            )
    return out


def check(wav_path: str, threshold: float = _THRESHOLD) -> list[MusicSegment]:
    """Screen a mono wav for music-likely segments."""
    return flag_segments(music_scores(wav_path), threshold)


def mute_segments(video_in: str, video_out: str, segments: list[MusicSegment]) -> str:
    """Mute the flagged segments in a video's audio track (video stream copied)."""
    if not segments:
        raise ValueError("no segments to mute")
    expr = "+".join(f"between(t,{s.start:.2f},{s.end:.2f})" for s in segments)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", video_in,
            "-af", f"volume=enable='{expr}':volume=0",
            "-c:v", "copy", "-c:a", "aac", video_out,
        ],
        check=True,
    )
    return video_out


def identify_segments(wav_path: str, segments: list[MusicSegment]) -> list[dict]:
    """Identify tracks in flagged segments via a fingerprinting provider. TODO.

    Integration point for AudD / ACRCloud: cut each segment to a short sample,
    post to the provider, return matches with confidence + track metadata.
    Only fingerprint flagged segments - that keeps per-clip lookup cost near zero.
    """
    raise NotImplementedError("fingerprinting provider integration is Phase 2")
