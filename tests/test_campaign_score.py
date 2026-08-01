from clipengine.campaigns.models import Campaign
from clipengine.campaigns.score import (
    DEFAULT_FAMILIARITY,
    familiarity_for,
    rank,
    score_campaign,
)


def _campaign(**over):
    base = dict(
        id="bnty_1", source="whop_bounty", title="Clip campaign",
        status="open", reward_model="per_submission", reward_amount=50.0,
        budget_total=1000.0, budget_remaining=800.0,
    )
    base.update(over)
    return Campaign(**base)


def test_higher_reward_scores_higher():
    lo = score_campaign(_campaign(reward_amount=10.0))
    hi = score_campaign(_campaign(reward_amount=100.0))
    assert hi.score > lo.score


def test_more_remaining_budget_scores_higher():
    lo = score_campaign(_campaign(budget_remaining=100.0))
    hi = score_campaign(_campaign(budget_remaining=5000.0))
    assert hi.score > lo.score


def test_budget_has_diminishing_returns():
    s1 = score_campaign(_campaign(budget_remaining=500.0)).score
    s2 = score_campaign(_campaign(budget_remaining=50000.0)).score
    assert s2 < s1 * 100  # 100x pool is nowhere near 100x score


def test_simple_rules_score_higher():
    simple = score_campaign(_campaign(rules_text=""))
    fussy = score_campaign(_campaign(
        rules_text="Must use #a #b #c #d, tag @e, at least 60 seconds, "
                   "no memes, do not crop, never speed up"
    ))
    assert simple.score > fussy.score


def test_familiar_source_scores_higher():
    keywords = {"valorant": 1.2}
    known = score_campaign(_campaign(title="Valorant highlights"), keywords)
    unknown = score_campaign(_campaign(title="Obscure game"), keywords)
    assert known.score > unknown.score
    assert known.breakdown["familiarity"] == 1.2
    assert unknown.breakdown["familiarity"] == DEFAULT_FAMILIARITY


def test_familiarity_matches_brand_and_rules():
    assert familiarity_for(_campaign(brand="BrandCo"), {"brandco": 1.5}) == 1.5
    assert familiarity_for(_campaign(rules_text="clip twitch.tv/somestreamer"),
                           {"somestreamer": 1.1}) == 1.1


def test_closed_campaign_scores_zero():
    assert score_campaign(_campaign(status="completed")).score == 0.0


def test_rank_orders_descending_and_keeps_breakdown():
    scored = rank([
        _campaign(id="a", reward_amount=5.0),
        _campaign(id="b", reward_amount=500.0),
        _campaign(id="c", status="canceled"),
    ])
    assert [s.campaign.id for s in scored] == ["b", "a", "c"]
    assert set(scored[0].breakdown) == {"rate", "budget", "familiarity", "simplicity"}


def test_cpm_campaign_scores_on_same_scale():
    cpm = score_campaign(_campaign(
        id="manual:x", source="manual", reward_model="cpm",
        reward_amount=2.0, budget_remaining=5000.0,
    ))
    assert cpm.score > 0
