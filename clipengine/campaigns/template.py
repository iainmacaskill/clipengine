"""Per-campaign render templates: bake rule compliance into the render.

Dev brief Phase 2: "Templates are per-campaign so rule compliance is baked
into the render, not left to the operator." Derived entirely from the
campaign's parsed rules — the same checklist the gate enforces — so what the
template bakes in is exactly what the gate later verifies:

- credit_text: required mentions burned into the clip
- caption_suffix: required hashtags/mentions appended to every caption
- duration bounds: the detector's target window is steered inside the
  campaign's min/max before anything renders

The gate stays in the loop after rendering (belt and braces): a templated
clip should pass it by construction, and the manifest records the proof.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Campaign
from .rules import Checklist, parse_rules

DURATION_MARGIN_S = 5.0  # render safely inside hard bounds, not on the edge


@dataclass
class CampaignTemplate:
    campaign_id: str
    checklist: Checklist
    credit_text: str = ""
    caption_suffix: str = ""
    min_duration_s: float | None = None
    max_duration_s: float | None = None
    platforms: list[str] = field(default_factory=list)


def template_for(campaign: Campaign) -> CampaignTemplate:
    check = parse_rules(campaign.rules_text)
    return CampaignTemplate(
        campaign_id=campaign.id,
        checklist=check,
        credit_text=" ".join(f"@{m}" for m in check.mentions),
        caption_suffix=" ".join(
            [f"#{h}" for h in check.hashtags] + [f"@{m}" for m in check.mentions]
        ),
        min_duration_s=check.min_duration_s,
        max_duration_s=check.max_duration_s,
        platforms=list(check.platforms),
    )


def effective_target(
    template: CampaignTemplate, base_target: float, margin: float = DURATION_MARGIN_S
) -> float:
    """Steer the detector's target duration inside the campaign's bounds.

    Sits ``margin`` seconds inside a hard bound so a rendered clip never
    lands exactly on the edge. When the margins don't fit between tight
    bounds, the midpoint wins.
    """
    lo, hi = template.min_duration_s, template.max_duration_s
    if lo is not None and hi is not None and lo + margin > hi - margin:
        return (lo + hi) / 2.0
    target = base_target
    if hi is not None:
        target = min(target, hi - margin)
    if lo is not None:
        target = max(target, lo + margin)
    return target


def build_caption(text: str, template: CampaignTemplate) -> str:
    """Append the required hashtags/mentions the text doesn't already carry."""
    lowered = text.lower()
    missing = [
        token
        for token in template.caption_suffix.split()
        if token.lower() not in lowered
    ]
    return " ".join(part for part in [text.strip(), " ".join(missing)] if part)


def merge_credit(base_credit: str, template: CampaignTemplate) -> str:
    """Combine the streamer's roster credit with the campaign's mandated credit."""
    campaign_credit = template.credit_text.strip()
    base = base_credit.strip()
    if not campaign_credit:
        return base
    if campaign_credit.lower() in base.lower():
        return base
    return f"{base} | {campaign_credit}" if base else campaign_credit
