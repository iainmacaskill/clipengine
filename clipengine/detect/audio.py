"""Audio-energy detection signal: per-second RMS loudness from the source audio.

Shouting, laughter, and sudden silence all move this series; fused with chat it
localises the moment more precisely than chat alone (chat reacts a few seconds late).
"""
from __future__ import annotations

import subprocess
import wave

import numpy as np

from ..models import SignalSeries


def extract_wav(video_path: str, wav_path: str, sample_rate: int = 16000) -> str:
    """Extract mono 16 kHz PCM audio from a video with ffmpeg."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
            "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", wav_path,
        ],
        check=True,
    )
    return wav_path


def energy_series(wav_path: str) -> SignalSeries:
    """Per-second RMS energy of a mono PCM wav."""
    with wave.open(wav_path, "rb") as wf:
        rate = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    seconds = int(np.ceil(len(samples) / rate))
    scores = []
    for i in range(seconds):
        chunk = samples[i * rate : (i + 1) * rate]
        rms = float(np.sqrt(np.mean(chunk**2))) if len(chunk) else 0.0
        scores.append(rms)
    return SignalSeries("audio_energy", scores)
