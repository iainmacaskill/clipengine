"""Chat-derived detection signals: message velocity and emote/reaction spikes.

Chat is the highest-value cheap signal: a burst of messages (or of LUL/KEKW-class
emotes) seconds after a moment is the audience marking the highlight for us.
"""
from __future__ import annotations

import json

from ..models import ChatMessage, SignalSeries


def parse_chat_jsonl(path: str) -> list[ChatMessage]:
    """Parse a chat log in JSON-lines form: {"offset": s, "user": u, "text": t}.

    This is the normalised format `ingest` writes; adapters for Twitch's raw
    comment format live in ingest/twitch.py.
    """
    messages = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            messages.append(
                ChatMessage(offset=float(d["offset"]), user=d.get("user", ""), text=d["text"])
            )
    messages.sort(key=lambda m: m.offset)
    return messages


def _bucket(messages: list[ChatMessage], duration: float) -> list[list[ChatMessage]]:
    n = int(duration) + 1
    buckets: list[list[ChatMessage]] = [[] for _ in range(n)]
    for m in messages:
        i = int(m.offset)
        if 0 <= i < n:
            buckets[i].append(m)
    return buckets


def velocity_series(messages: list[ChatMessage], duration: float) -> SignalSeries:
    """Messages per second."""
    buckets = _bucket(messages, duration)
    return SignalSeries("chat_velocity", [float(len(b)) for b in buckets])


def emote_series(
    messages: list[ChatMessage], duration: float, emote_tokens: list[str]
) -> SignalSeries:
    """Count of reaction-emote tokens per second (case-sensitive, word-level)."""
    tokens = set(emote_tokens)
    buckets = _bucket(messages, duration)
    scores = []
    for b in buckets:
        count = 0
        for m in b:
            count += sum(1 for w in m.text.split() if w in tokens)
        scores.append(float(count))
    return SignalSeries("chat_emotes", scores)
