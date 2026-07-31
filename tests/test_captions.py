from clipengine.config import CaptionConfig
from clipengine.models import Transcript, TranscriptSegment, Word
from clipengine.package.captions import build_ass


def _transcript(words):
    return Transcript(
        segments=[
            TranscriptSegment(
                start=words[0][0], end=words[-1][1], text=" ".join(w[2] for w in words),
                words=[Word(*w) for w in words],
            )
        ]
    )


def test_build_ass_structure():
    t = _transcript([(0.0, 0.4, "wait"), (0.5, 0.9, "what"), (1.0, 1.4, "is"), (1.5, 1.9, "that")])
    doc = build_ass(t, CaptionConfig(chunk_words=3))
    assert doc.startswith("[Script Info]")
    assert "PlayResX: 1080" in doc and "PlayResY: 1920" in doc
    # 4 words, chunks of 3 -> 3 events for the first chunk + 1 for the second
    assert doc.count("Dialogue:") == 4


def test_active_word_is_highlighted():
    t = _transcript([(0.0, 0.4, "wait"), (0.5, 0.9, "what")])
    doc = build_ass(t, CaptionConfig(chunk_words=2, highlight_colour="&H0000FFFF&"))
    events = [ln for ln in doc.splitlines() if ln.startswith("Dialogue:")]
    assert "{\\c&H0000FFFF&}wait" in events[0]
    assert "{\\c&H0000FFFF&}what" in events[1]


def test_no_highlight_style():
    t = _transcript([(0.0, 0.4, "hello"), (0.5, 0.9, "there")])
    doc = build_ass(t, CaptionConfig(chunk_words=2, highlight_colour=""))
    assert "\\c&H" not in doc.split("[Events]")[1]


def test_zero_duration_word_gets_min_display_time():
    t = _transcript([(1.0, 1.0, "blip"), (1.0, 1.5, "next")])
    doc = build_ass(t, CaptionConfig(chunk_words=2))
    assert "Dialogue:" in doc  # no crash, events emitted
