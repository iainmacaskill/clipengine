#!/usr/bin/env python3
"""PocketSphinx transcription emitting whisper-style JSON (segments[].words[])."""
import json, sys, wave
from pocketsphinx import Decoder

src, out = sys.argv[1], sys.argv[2]
dec = Decoder(samprate=16000)
wf = wave.open(src, "rb")
assert wf.getframerate() == 16000 and wf.getnchannels() == 1

dec.start_utt()
while True:
    buf = wf.readframes(4096)
    if not buf:
        break
    dec.process_raw(buf, False, False)
dec.end_utt()

words = []
for seg in dec.seg():
    w = seg.word
    if w in ("<s>", "</s>", "<sil>", "(NULL)") or w.startswith("["):
        continue
    words.append({"start": seg.start_frame / 100.0, "end": seg.end_frame / 100.0,
                  "word": w.split("(")[0]})

# group words into segments on gaps > 0.6s
segments, cur = [], []
for w in words:
    if cur and w["start"] - cur[-1]["end"] > 0.6:
        segments.append(cur); cur = []
    cur.append(w)
if cur:
    segments.append(cur)

data = {"segments": [{"start": s[0]["start"], "end": s[-1]["end"],
                      "text": " ".join(w["word"] for w in s), "words": s}
                     for s in segments]}
json.dump(data, open(out, "w"), indent=1)
for s in data["segments"]:
    print(f"[{s['start']:6.2f} - {s['end']:6.2f}] {s['text']}")
