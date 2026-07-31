"""ASR via faster-whisper (optional dependency: `pip install clipengine[asr]`).

Detection works without a transcript (chat + audio carry most of the signal);
the transcript is required for captions and improves title/hook generation.
"""
from __future__ import annotations

import json

from ..models import Transcript, TranscriptSegment, Word


def transcribe(audio_path: str, model_size: str = "tiny.en") -> Transcript:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper not installed - run: pip install 'clipengine[asr]'"
        ) from e

    model = WhisperModel(model_size, device="auto", compute_type="int8")
    raw_segments, _info = model.transcribe(audio_path, word_timestamps=True)
    segments = [
        TranscriptSegment(
            start=s.start,
            end=s.end,
            text=s.text,
            words=[Word(w.start, w.end, w.word.strip()) for w in (s.words or [])],
        )
        for s in raw_segments
    ]
    return Transcript(segments=segments)


def save(transcript: Transcript, path: str) -> None:
    data = {
        "segments": [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "words": [{"start": w.start, "end": w.end, "word": w.text} for w in s.words],
            }
            for s in transcript.segments
        ]
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def load(path: str) -> Transcript:
    with open(path) as f:
        data = json.load(f)
    return Transcript(
        segments=[
            TranscriptSegment(
                start=s["start"],
                end=s["end"],
                text=s.get("text", ""),
                words=[Word(w["start"], w["end"], w["word"].strip()) for w in s.get("words", [])],
            )
            for s in data["segments"]
        ]
    )
