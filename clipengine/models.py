"""Core data types shared across pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    """One chat message, timestamped in seconds relative to stream/VOD start."""

    offset: float
    user: str
    text: str


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    segments: list[TranscriptSegment]

    def words(self) -> list[Word]:
        return [w for s in self.segments for w in s.words]

    def text_between(self, start: float, end: float) -> str:
        return " ".join(
            s.text.strip() for s in self.segments if s.end > start and s.start < end
        )


@dataclass
class SignalSeries:
    """A per-second score series for one detection signal.

    `scores[i]` covers the source timeline second `[i, i+1)`.
    """

    name: str
    scores: list[float]


@dataclass
class ClipCandidate:
    """A scored highlight window proposed by the detector."""

    start: float
    end: float
    score: float
    signal_breakdown: dict[str, float] = field(default_factory=dict)
    title_hint: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class FacecamRegion:
    """Facecam bounding box in source pixel space."""

    x: int
    y: int
    w: int
    h: int


@dataclass
class SourceVideo:
    path: str
    width: int
    height: int
    duration: float
    streamer: str = ""
    vod_id: str = ""
    facecam: FacecamRegion | None = None
