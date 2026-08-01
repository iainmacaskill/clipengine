from clipengine.campaigns.models import Campaign
from clipengine.campaigns.store import CampaignStore


def _campaign(cid="bnty_1", **over):
    base = dict(
        id=cid, source="whop_bounty", title="Clip campaign", brand="BrandCo",
        goal_type="clipping", status="open", reward_model="per_submission",
        reward_amount=50.0, budget_total=1000.0, budget_remaining=800.0,
        spots_remaining=16, paid_out=200.0, unresolved=3,
        platforms=["tiktok"], rules_text="Use #brand", created_at="2026-08-01",
    )
    base.update(over)
    return Campaign(**base)


def _store(tmp_path):
    return CampaignStore(str(tmp_path / "campaigns.db"))


def test_upsert_returns_only_new_campaigns(tmp_path):
    with _store(tmp_path) as store:
        new = store.upsert([_campaign("bnty_1"), _campaign("bnty_2")], at="t1")
        assert [c.id for c in new] == ["bnty_1", "bnty_2"]
        new = store.upsert([_campaign("bnty_1"), _campaign("bnty_3")], at="t2")
        assert [c.id for c in new] == ["bnty_3"]


def test_roundtrip_preserves_fields(tmp_path):
    with _store(tmp_path) as store:
        store.upsert([_campaign()], at="t1")
        c = store.get("bnty_1")
        assert c is not None
        assert c.platforms == ["tiktok"]
        assert c.spots_remaining == 16
        assert c.rules_text == "Use #brand"
        assert c.budget_remaining == 800.0


def test_update_refreshes_budget_state(tmp_path):
    with _store(tmp_path) as store:
        store.upsert([_campaign()], at="t1")
        store.upsert([_campaign(budget_remaining=300.0, status="closed")], at="t2")
        c = store.get("bnty_1")
        assert c.budget_remaining == 300.0 and c.status == "closed"


def test_shallow_sync_keeps_stored_rules(tmp_path):
    """A --no-rules sync must not blank rules captured by an earlier full sync."""
    with _store(tmp_path) as store:
        store.upsert([_campaign(rules_text="Use #brand")], at="t1")
        store.upsert([_campaign(rules_text="")], at="t2")
        assert store.get("bnty_1").rules_text == "Use #brand"


def test_snapshots_accumulate_depletion_history(tmp_path):
    with _store(tmp_path) as store:
        store.upsert([_campaign(budget_remaining=800.0)], at="t1")
        store.upsert([_campaign(budget_remaining=500.0)], at="t2")
        store.upsert([_campaign(budget_remaining=100.0)], at="t3")
        history = store.history("bnty_1")
        assert [(s.at, s.budget_remaining) for s in history] == [
            ("t1", 800.0), ("t2", 500.0), ("t3", 100.0)
        ]


def test_list_filters_by_status(tmp_path):
    with _store(tmp_path) as store:
        store.upsert([_campaign("bnty_1"), _campaign("bnty_2", status="closed")], at="t1")
        assert [c.id for c in store.list(status="open")] == ["bnty_1"]
        assert len(store.list()) == 2


def test_manual_cpm_campaign_coexists(tmp_path):
    with _store(tmp_path) as store:
        store.upsert([
            _campaign(),
            _campaign("manual:neon-clips", source="manual", reward_model="cpm",
                      reward_amount=2.0, spots_remaining=None,
                      url="https://whop.com/example"),
        ], at="t1")
        c = store.get("manual:neon-clips")
        assert c.reward_model == "cpm" and c.spots_remaining is None
        assert c.url == "https://whop.com/example"
