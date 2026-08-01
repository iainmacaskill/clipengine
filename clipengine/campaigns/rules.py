"""Campaign rules parser: free-form brief text -> structured checklist.

The checklist is what the Phase 2 compliance gate enforces before any clip
exports (every rejected clip is unpaid work), and its complexity feeds the
scoring model — simple rules mean fewer rejections, so they score higher.

Heuristic extraction, deliberately conservative: anything it cannot classify
stays visible in ``rules_text`` for the operator; the parser never invents
requirements.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# platform keyword -> canonical name
_PLATFORMS = {
    "tiktok": "tiktok",
    "tik tok": "tiktok",
    "youtube": "youtube",
    "shorts": "youtube",
    "instagram": "instagram",
    "reels": "instagram",
    "twitter": "x",
    "facebook": "facebook",
}

_HASHTAG = re.compile(r"#([A-Za-z0-9_]+)")
_MENTION = re.compile(r"@([A-Za-z0-9_.]{2,})")
_LINK = re.compile(r"https?://\S+")
# "at least 30 seconds", "minimum 1 minute", "30s minimum", "30+ seconds"
_MIN_DUR = re.compile(
    r"(?:at least|minimum(?: of)?|min\.?|longer than|more than|over)\s+"
    r"(\d+)\s*(seconds?|secs?|s\b|minutes?|min\b)"
    r"|(\d+)\s*(seconds?|secs?|s\b|minutes?|min\b)\s+(?:minimum|or longer|or more)"
    r"|(\d+)\+\s*(seconds?|secs?|s\b|minutes?|min\b)",
    re.I,
)
_MAX_DUR = re.compile(
    r"(?:at most|under|max(?:imum)?(?: of)?|no longer than|less than|shorter than|up to)"
    r"\s+(\d+)\s*(seconds?|secs?|s\b|minutes?|min\b)",
    re.I,
)
_RANGE_DUR = re.compile(
    r"(\d+)\s*[-–]\s*(\d+)\s*(seconds?|secs?|s\b|minutes?|min\b)", re.I
)
_BANNED_LINE = re.compile(
    r"^\s*(?:[-*•]\s*)?(no |don'?t |do not |never |avoid )|"
    r"(not allowed|banned|prohibited|forbidden|must not|will be rejected)",
    re.I,
)
_REQUIRED_LINE = re.compile(r"\b(must|required?|include|credit|tag|mention|use)\b", re.I)


def _seconds(n: str, unit: str) -> float:
    return float(n) * (60.0 if unit.lower().startswith("min") else 1.0)


@dataclass
class Checklist:
    hashtags: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    min_duration_s: float | None = None
    max_duration_s: float | None = None
    platforms: list[str] = field(default_factory=list)
    required: list[str] = field(default_factory=list)  # must/include/credit lines
    banned: list[str] = field(default_factory=list)    # no/don't/prohibited lines
    links: list[str] = field(default_factory=list)     # source-material links

    @property
    def complexity(self) -> int:
        """Count of distinct requirements a clip can fail on."""
        return (
            len(self.hashtags) + len(self.mentions)
            + len(self.required) + len(self.banned)
            + (1 if self.min_duration_s is not None else 0)
            + (1 if self.max_duration_s is not None else 0)
            + (1 if self.platforms else 0)
        )

    @property
    def simplicity(self) -> float:
        """(0, 1]: 1.0 for no constraints, decaying as requirements stack up."""
        return 1.0 / (1.0 + 0.15 * self.complexity)


def parse_rules(text: str) -> Checklist:
    check = Checklist()
    if not text.strip():
        return check
    check.hashtags = _dedupe(m.group(1) for m in _HASHTAG.finditer(text))
    check.mentions = _dedupe(
        h for m in _MENTION.finditer(text) if len(h := m.group(1).rstrip(".")) >= 2
    )
    check.links = _dedupe(m.group(0).rstrip(".,)") for m in _LINK.finditer(text))

    m = _RANGE_DUR.search(text)
    if m:
        check.min_duration_s = _seconds(m.group(1), m.group(3))
        check.max_duration_s = _seconds(m.group(2), m.group(3))
    else:
        m = _MIN_DUR.search(text)
        if m:
            n, unit = next(
                (m.group(i), m.group(i + 1)) for i in (1, 3, 5) if m.group(i)
            )
            check.min_duration_s = _seconds(n, unit)
        m = _MAX_DUR.search(text)
        if m:
            check.max_duration_s = _seconds(m.group(1), m.group(2))

    lowered = text.lower()
    check.platforms = _dedupe(
        canon for kw, canon in _PLATFORMS.items() if kw in lowered
    )

    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        if _BANNED_LINE.search(line):
            check.banned.append(line)
        elif _REQUIRED_LINE.search(line):
            check.required.append(line)
    return check


def _dedupe(items) -> list[str]:
    seen: dict[str, None] = {}
    for it in items:
        seen.setdefault(it)
    return list(seen)
