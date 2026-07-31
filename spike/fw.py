#!/usr/bin/env python3
"""faster-whisper wrapper emitting openai-whisper-style JSON (segments[].words[])."""
import json, sys
from faster_whisper import WhisperModel

src, out = sys.argv[1], sys.argv[2]
model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
segments, info = model.transcribe(src, word_timestamps=True, language="en")
data = {"segments": []}
for seg in segments:
    data["segments"].append({
        "start": seg.start, "end": seg.end, "text": seg.text,
        "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (seg.words or [])],
    })
json.dump(data, open(out, "w"), indent=1)
for s in data["segments"]:
    print(f"[{s['start']:6.2f} - {s['end']:6.2f}] {s['text']}")
