"""Compliance gate: pre-flight a rendered clip against a campaign's checklist.

Dev brief Phase 2: "Nothing exports without a pass. Every rejected clip is
unpaid work." The gate verifies everything machine-checkable — duration
bounds, required hashtags/mentions in the caption, target platform, campaign
still open with budget left, source authorisation — and surfaces what it
cannot verify (free-text requirements, banned edit styles) as explicit
manual-confirmation items instead of silently passing them.

Statuses per check: ``pass`` / ``fail`` / ``manual``. The gate passes when
nothing failed; manual items ride along for the operator (the review queue is
where they get confirmed).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Campaign
from .rules import Checklist, line_has_structured_requirement

PASS, FAIL, MANUAL = "pass", "fail", "manual"


@dataclass
class ClipFacts:
    """What we know about the clip being exported."""

    duration_s: float
    caption: str = ""      # full posted text: title/caption + description + tags
    credit_text: str = ""  # credit burned into the video, if any
    platform: str = ""     # canonical target: tiktok|youtube|instagram|x|facebook
    source_url: str = ""   # where the footage came from


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


@dataclass
class GateReport:
    campaign_id: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == FAIL]

    @property
    def manual(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == MANUAL]


def _norm_url(url: str) -> str:
    url = url.lower().strip()
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
    if url.startswith("www."):
        url = url[4:]
    return url.rstrip("/")


def preflight(
    facts: ClipFacts, checklist: Checklist, campaign: Campaign | None = None
) -> GateReport:
    report = GateReport(campaign_id=campaign.id if campaign else "")
    add = report.results.append

    if campaign is not None:
        if not campaign.open:
            add(CheckResult("campaign", FAIL,
                            f"campaign is {campaign.status} - submissions won't pay"))
        elif campaign.budget_remaining <= 0:
            add(CheckResult("campaign", FAIL,
                            "campaign budget exhausted - submissions won't pay"))
        else:
            add(CheckResult("campaign", PASS,
                            f"open, {campaign.budget_remaining:g} {campaign.currency} remaining"))

    if checklist.min_duration_s is not None:
        if facts.duration_s < checklist.min_duration_s:
            add(CheckResult("duration", FAIL,
                            f"{facts.duration_s:.1f}s is under the "
                            f"{checklist.min_duration_s:g}s minimum"))
        else:
            add(CheckResult("duration", PASS,
                            f"{facts.duration_s:.1f}s >= {checklist.min_duration_s:g}s"))
    if checklist.max_duration_s is not None:
        if facts.duration_s > checklist.max_duration_s:
            add(CheckResult("duration", FAIL,
                            f"{facts.duration_s:.1f}s is over the "
                            f"{checklist.max_duration_s:g}s maximum"))
        else:
            add(CheckResult("duration", PASS,
                            f"{facts.duration_s:.1f}s <= {checklist.max_duration_s:g}s"))

    caption = facts.caption.lower()
    credited = f"{facts.caption} {facts.credit_text}".lower()
    for tag in checklist.hashtags:
        if f"#{tag.lower()}" in caption:
            add(CheckResult("hashtag", PASS, f"#{tag} present"))
        else:
            add(CheckResult("hashtag", FAIL, f"#{tag} missing from caption"))
    for mention in checklist.mentions:
        if f"@{mention.lower()}" in credited:
            add(CheckResult("mention", PASS, f"@{mention} present"))
        else:
            add(CheckResult("mention", FAIL,
                            f"@{mention} missing from caption and credit"))

    if checklist.platforms and facts.platform:
        if facts.platform in checklist.platforms:
            add(CheckResult("platform", PASS, f"{facts.platform} is allowed"))
        else:
            add(CheckResult("platform", FAIL,
                            f"{facts.platform} not in allowed platforms: "
                            f"{', '.join(checklist.platforms)}"))

    if checklist.links:
        source = _norm_url(facts.source_url)
        matched = source and any(
            source in _norm_url(link) or _norm_url(link) in source
            for link in checklist.links
        )
        if matched:
            add(CheckResult("source", PASS, f"source matches {facts.source_url}"))
        else:
            add(CheckResult("source", MANUAL,
                            "confirm footage comes from the campaign's sources: "
                            + ", ".join(checklist.links)))

    for line in checklist.required:
        if not line_has_structured_requirement(line):
            add(CheckResult("required", MANUAL, f"confirm: {line}"))
    for line in checklist.banned:
        add(CheckResult("banned", MANUAL, f"confirm clip avoids: {line}"))

    return report
