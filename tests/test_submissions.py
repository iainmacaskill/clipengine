import pytest

from clipengine.campaigns.models import Campaign
from clipengine.campaigns.submissions import SubmissionStore, expected_amount

T0 = "2026-08-01T12:00:00+00:00"
T_47H = "2026-08-03T10:59:00+00:00"
T_49H = "2026-08-03T13:00:00+00:00"


@pytest.fixture
def store(tmp_path):
    with SubmissionStore(str(tmp_path / "campaigns.db")) as s:
        yield s


def _cpm_campaign(cid="manual:neon", cpm=2.0):
    return Campaign(
        id=cid, source="manual", title="Neon clips", reward_model="cpm",
        reward_amount=cpm, budget_total=5000.0, budget_remaining=5000.0,
    )


def _bounty_campaign(cid="bnty_1", reward=50.0):
    return Campaign(
        id=cid, source="whop_bounty", title="Bounty", reward_model="per_submission",
        reward_amount=reward, budget_total=1000.0, budget_remaining=1000.0,
    )


# -- lifecycle -------------------------------------------------------------


def test_add_starts_pending(store):
    sub = store.add("manual:neon", "https://tiktok.com/@me/video/1", at=T0)
    assert sub.status == "pending" and sub.submitted_at == T0


def test_duplicate_submission_refused(store):
    store.add("manual:neon", "https://tiktok.com/@me/video/1")
    with pytest.raises(ValueError, match="already tracked"):
        store.add("manual:neon", "https://tiktok.com/@me/video/1")
    # same URL to a different campaign is a separate submission
    store.add("bnty_2", "https://tiktok.com/@me/video/1")


def test_empty_url_refused(store):
    with pytest.raises(ValueError, match="post URL required"):
        store.add("manual:neon", "  ")


def test_approve_then_paid(store):
    sub = store.add("manual:neon", "https://x/1", at=T0)
    sub = store.approve(sub.id, at="2026-08-02T12:00:00+00:00")
    assert sub.status == "approved"
    sub = store.mark_paid(sub.id, 12.5, at="2026-08-03T12:00:00+00:00")
    assert sub.status == "paid" and sub.amount == 12.5
    assert sub.approved_at == "2026-08-02T12:00:00+00:00"  # not overwritten


def test_paid_from_pending_backfills_approval(store):
    sub = store.add("manual:neon", "https://x/1", at=T0)
    sub = store.mark_paid(sub.id, 5.0, at=T_49H)
    assert sub.status == "paid" and sub.approved_at == T_49H


def test_reject_requires_reason_and_blocks_payment(store):
    sub = store.add("manual:neon", "https://x/1")
    with pytest.raises(ValueError, match="reason required"):
        store.reject(sub.id, "  ")
    store.reject(sub.id, "wrong aspect ratio")
    with pytest.raises(ValueError, match="rejected"):
        store.mark_paid(sub.id, 5.0)


def test_cannot_approve_twice(store):
    sub = store.add("manual:neon", "https://x/1")
    store.approve(sub.id)
    with pytest.raises(ValueError, match="only pending"):
        store.approve(sub.id)


def test_invalid_amounts_and_views(store):
    sub = store.add("manual:neon", "https://x/1")
    with pytest.raises(ValueError):
        store.mark_paid(sub.id, 0)
    with pytest.raises(ValueError):
        store.set_views(sub.id, -1)
    with pytest.raises(LookupError):
        store.get(999)


# -- 48h auto-approval window ---------------------------------------------


def test_auto_approve_only_past_window(store):
    old = store.add("manual:neon", "https://x/old", at=T0)
    fresh = store.add("manual:neon", "https://x/fresh", at="2026-08-03T09:00:00+00:00")
    moved = store.auto_approve(now=T_49H)
    assert [s.id for s in moved] == [old.id]
    assert store.get(old.id).status == "approved"
    assert "auto-approved" in store.get(old.id).notes
    assert store.get(fresh.id).status == "pending"


def test_auto_approve_timestamps_at_window_end_not_now(store):
    sub = store.add("manual:neon", "https://x/1", at=T0)
    (moved,) = store.auto_approve(now="2026-08-10T00:00:00+00:00")
    assert moved.approved_at == "2026-08-03T12:00:00+00:00"  # T0 + 48h


def test_auto_approve_before_window_does_nothing(store):
    store.add("manual:neon", "https://x/1", at=T0)
    assert store.auto_approve(now=T_47H) == []


# -- earnings rollup -------------------------------------------------------


def test_expected_amount_by_reward_model(store):
    sub = store.add("manual:neon", "https://x/1")
    sub = store.set_views(sub.id, 25000)
    assert expected_amount(sub, _cpm_campaign(cpm=2.0)) == 50.0
    assert expected_amount(sub, _bounty_campaign(reward=40.0)) == 40.0
    assert expected_amount(sub, None) == 0.0


def test_earnings_rollup(store):
    campaigns = {"manual:neon": _cpm_campaign(), "bnty_1": _bounty_campaign()}
    a = store.add("manual:neon", "https://x/1", at=T0)
    store.set_views(a.id, 10000)
    store.mark_paid(a.id, 20.0, at="2026-08-02T12:00:00+00:00")
    b = store.add("manual:neon", "https://x/2", at=T0)
    store.set_views(b.id, 5000)  # pending: expected 5000/1000*2 = 10
    c = store.add("manual:neon", "https://x/3", at=T0)
    store.reject(c.id, "off-brand")
    d = store.add("bnty_1", "https://x/4", at=T0)
    store.approve(d.id, at="2026-08-01T18:00:00+00:00")  # 6h to approval

    by_id = {e.campaign_id: e for e in store.earnings(campaigns)}
    neon = by_id["manual:neon"]
    assert (neon.total, neon.paid, neon.pending, neon.rejected) == (3, 1, 1, 1)
    assert neon.paid_amount == 20.0
    assert neon.expected_amount == 10.0
    assert neon.views == 15000
    assert neon.rejection_rate == 0.5  # 1 of 2 resolved
    assert neon.effective_cpm == pytest.approx(20.0 / 15000 * 1000)
    bounty = by_id["bnty_1"]
    assert bounty.expected_amount == 50.0  # per-submission reward
    assert bounty.avg_hours_to_approval == pytest.approx(6.0)
    assert bounty.rejection_rate == 0.0
    # ordered by paid amount
    assert [e.campaign_id for e in store.earnings(campaigns)][0] == "manual:neon"


def test_rejection_rate_none_until_resolved(store):
    store.add("manual:neon", "https://x/1")
    (e,) = store.earnings()
    assert e.rejection_rate is None and e.effective_cpm is None


# -- CLI wiring ------------------------------------------------------------


@pytest.fixture
def env(tmp_path):
    from clipengine.campaigns.store import CampaignStore

    cfg = tmp_path / "cfg.toml"
    cfg.write_text(f'[campaigns]\ncampaigns_db = "{tmp_path / "campaigns.db"}"\n')
    with CampaignStore(str(tmp_path / "campaigns.db")) as cstore:
        cstore.upsert([_cpm_campaign()], at="t1")
    return str(cfg)


def _cli(env, *argv):
    from clipengine import cli

    return cli.main(["--config", env, "submissions", *argv])


def test_cli_add_list_paid_stats(env, capsys):
    rc = _cli(env, "add", "manual:neon", "https://tiktok.com/@me/video/1",
              "--platform", "tiktok", "--account", "acct1")
    assert rc == 0
    assert "pending" in capsys.readouterr().out

    assert _cli(env, "views", "1", "10000") == 0
    capsys.readouterr()
    assert _cli(env, "paid", "1", "--amount", "20") == 0
    assert "$" in capsys.readouterr().out

    assert _cli(env, "stats") == 0
    out = capsys.readouterr().out
    assert "paid 20" in out
    assert "effective CPM 2.00/1k" in out
    assert "TOTAL paid 20" in out


def test_cli_add_unknown_campaign(env, capsys):
    assert _cli(env, "add", "nope", "https://x/1") == 1
    assert "unknown campaign" in capsys.readouterr().err


def test_cli_reject_needs_reason_flag_and_records_it(env, capsys):
    _cli(env, "add", "manual:neon", "https://x/1")
    capsys.readouterr()
    assert _cli(env, "reject", "1", "--reason", "wrong ratio") == 0
    assert "wrong ratio" in capsys.readouterr().out


def test_cli_duplicate_add_exits_1(env, capsys):
    _cli(env, "add", "manual:neon", "https://x/1")
    assert _cli(env, "add", "manual:neon", "https://x/1") == 1
    assert "already tracked" in capsys.readouterr().err


def test_cli_reconcile_offline(env, capsys):
    _cli(env, "add", "manual:neon", "https://x/1")
    capsys.readouterr()
    assert _cli(env, "reconcile") == 0
    out = capsys.readouterr().out
    assert "tracker:" in out and "--user" in out


def test_cli_reconcile_against_whop(env, monkeypatch, capsys):
    import httpx

    from clipengine.campaigns import whop

    def handler(request: httpx.Request) -> httpx.Response:
        if "/payouts" in request.url.path:
            return httpx.Response(200, json={"data": [
                {"id": "pay_1", "amount": 100.0, "status": "completed"},
                {"id": "pay_2", "amount": 40.0, "status": "in_transit"},
            ], "page_info": {}})
        return httpx.Response(200, json={"balance": {
            "balance": 55.0, "pending_balance": 12.0}})

    monkeypatch.setenv("CLIPENGINE_WHOP_API_KEY", "k")
    real_init = whop.WhopClient.__init__

    def patched(self, api_key, client=None, base_url=whop.BASE_URL):
        real_init(self, api_key,
                  client=httpx.Client(transport=httpx.MockTransport(handler)),
                  base_url=base_url)

    monkeypatch.setattr(whop.WhopClient, "__init__", patched)
    assert _cli(env, "reconcile", "--user", "user_1", "--ledger", "ldgr_1") == 0
    out = capsys.readouterr().out
    assert "100 withdrawn" in out  # in_transit not counted
    assert "balance 55" in out and "pending 12" in out
