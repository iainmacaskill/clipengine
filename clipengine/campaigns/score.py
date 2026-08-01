"""Campaign expected-value scoring (dev brief Phase 1).

score = rate × log1p(budget_remaining) × familiarity × rule_simplicity

- rate: reward per accepted submission (bounties) or per 1,000 verified
  views (CPM campaigns). The two models compete on the same scale on the
  grounds that one accepted submission and 1k verified views are comparable
  units of work for a short clip.
- log1p on remaining budget: a bigger pool means more headroom before
  first-come-first-served exhaustion, with diminishing returns — a $50k pool
  is not 100× better than a $500 one.
- familiarity: operator knowledge of the source material, from config
  keywords matched against title/brand/rules (0.5 unknown .. matched weight).
- rule_simplicity: from the parsed checklist — every requirement is a way to
  get rejected, and rejected clips are unpaid work.

Closed campaigns score 0. The formula is deliberately transparent: the
breakdown ships with the score so the operator can see *why* something ranks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Campaign
from .rules import Checklist, parse_rules

DEFAULT_FAMILIARITY = 0.5


@dataclass
class ScoredCampaign:
    campaign: Campaign
    checklist: Checklist
    score: float
    breakdown: dict[str, float]


def familiarity_for(campaign: Campaign, keywords: dict[str, float]) -> float:
    """Best matching keyword weight, or the unknown-source default.

    Keywords match case-insensitively against title, brand, and rules text —
    e.g. {"valorant": 1.0, "yourfavstreamer": 1.2}.
    """
    haystack = f"{campaign.title} {campaign.brand} {campaign.rules_text}".lower()
    matched = [w for kw, w in keywords.items() if kw.lower() in haystack]
    return max(matched) if matched else DEFAULT_FAMILIARITY


def score_campaign(
    campaign: Campaign, familiarity_keywords: dict[str, float] | None = None
) -> ScoredCampaign:
    checklist = parse_rules(campaign.rules_text)
    fam = familiarity_for(campaign, familiarity_keywords or {})
    if not campaign.open:
        parts = {"rate": 0.0, "budget": 0.0, "familiarity": fam,
                 "simplicity": checklist.simplicity}
        return ScoredCampaign(campaign, checklist, 0.0, parts)
    # the original /bounties surface doesn't expose a per-submission reward;
    # unknown rate scores neutral (1.0) so budget/familiarity/rules still rank
    rate = campaign.reward_amount if campaign.reward_amount > 0 else 1.0
    remaining = max(0.0, campaign.budget_remaining)
    # log1p gives diminishing returns on big pools; the saturation term sinks
    # nearly-exhausted ones - high-rate outliers on dying budgets are the
    # known trap (work delivered after the pool empties is unpaid)
    budget = math.log1p(remaining) * (remaining / (remaining + 1000.0))
    parts = {
        "rate": rate,
        "budget": round(budget, 3),
        "familiarity": fam,
        "simplicity": round(checklist.simplicity, 3),
    }
    return ScoredCampaign(
        campaign, checklist, rate * budget * fam * checklist.simplicity, parts
    )


def rank(
    campaigns: list[Campaign], familiarity_keywords: dict[str, float] | None = None
) -> list[ScoredCampaign]:
    scored = [score_campaign(c, familiarity_keywords) for c in campaigns]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored
