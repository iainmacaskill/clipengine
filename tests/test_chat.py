import json

from clipengine.detect import chat
from clipengine.models import ChatMessage


def _msgs(offsets_texts):
    return [ChatMessage(offset=o, user="u", text=t) for o, t in offsets_texts]


def test_parse_chat_jsonl(tmp_path):
    p = tmp_path / "chat.jsonl"
    lines = [
        {"offset": 5.2, "user": "a", "text": "LUL"},
        {"offset": 1.0, "user": "b", "text": "hello"},
    ]
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    msgs = chat.parse_chat_jsonl(str(p))
    assert [m.offset for m in msgs] == [1.0, 5.2]  # sorted


def test_velocity_series_counts_per_second():
    msgs = _msgs([(0.1, "a"), (0.9, "b"), (2.5, "c")])
    s = chat.velocity_series(msgs, duration=4.0)
    assert s.scores == [2.0, 0.0, 1.0, 0.0, 0.0]


def test_emote_series_counts_tokens_not_messages():
    msgs = _msgs([(1.2, "KEKW KEKW no way"), (1.8, "hello"), (3.0, "LUL")])
    s = chat.emote_series(msgs, duration=4.0, emote_tokens=["KEKW", "LUL"])
    assert s.scores == [0.0, 2.0, 0.0, 1.0, 0.0]


def test_out_of_range_messages_ignored():
    msgs = _msgs([(-1.0, "x"), (99.0, "y"), (1.0, "ok")])
    s = chat.velocity_series(msgs, duration=3.0)
    assert sum(s.scores) == 1.0
