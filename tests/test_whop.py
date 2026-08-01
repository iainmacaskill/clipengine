import json

import httpx
import pytest

from clipengine.campaigns.whop import WhopClient, WhopError


def _bounty(i, goal="clipping", **over):
    raw = {
        "id": f"bnty_{i}",
        "title": f"Clip campaign {i}",
        "status": "open",
        "business_goal_type": goal,
        "currency": "usd",
        "budget_amount": 1000.0,
        "gross_reward_amount": 50.0,
        "gross_paid_out_amount": 200.0,
        "accepted_submissions_count": 4,
        "accepted_submissions_limit": 20,
        "spots_remaining": 16,
        "unresolved_submissions_count": 3,
        "allowed_country_codes": [],
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-01T00:00:00Z",
        "funding_account": {"id": "biz_1", "title": "BrandCo"},
        "poster": {"id": "user_1", "username": "brandguy",
                   "profile_picture": {"url": "x"}},
    }
    raw.update(over)
    return raw


def _client(handler):
    return WhopClient("test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_requires_api_key():
    with pytest.raises(WhopError, match="API key"):
        WhopClient("")


def test_base_url_env_override(monkeypatch):
    monkeypatch.setenv("WHOP_BASE_URL", "http://127.0.0.1:9/api/v1/")
    hit = {}

    def handler(request: httpx.Request) -> httpx.Response:
        hit["url"] = str(request.url)
        return httpx.Response(200, json={"data": [], "page_info": {}})

    client = WhopClient("k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    client.list_bounties()
    assert hit["url"].startswith("http://127.0.0.1:9/api/v1/workforce/bounties")
    # explicit base_url beats the env
    client = WhopClient("k", client=httpx.Client(transport=httpx.MockTransport(handler)),
                        base_url="http://other/api/v1")
    client.list_bounties()
    assert hit["url"].startswith("http://other/api/v1/")


def test_list_bounties_paginates_and_stays_read_only():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-key"
        if request.url.params.get("after"):
            return httpx.Response(200, json={"data": [_bounty(3)], "page_info": {}})
        return httpx.Response(
            200,
            json={"data": [_bounty(1), _bounty(2)],
                  "page_info": {"end_cursor": "cur_2"}},
        )

    items = _client(handler).list_bounties()
    assert [b["id"] for b in items] == ["bnty_1", "bnty_2", "bnty_3"]
    assert len(requests) == 2
    assert requests[1].url.params["after"] == "cur_2"
    # read-only campaign discovery is a hard line (dev brief §4)
    assert all(r.method == "GET" for r in requests)


def test_campaigns_filters_goal_type_client_side():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [
            _bounty(1, goal="clipping"),
            _bounty(2, goal="post_engagement"),
            _bounty(3, goal="ugc_content"),
            _bounty(4, goal=None),
        ], "page_info": {}})

    campaigns = _client(handler).campaigns(with_rules=False)
    assert [c.id for c in campaigns] == ["bnty_1", "bnty_3"]


def test_campaigns_normalises_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [_bounty(1)], "page_info": {}})

    (c,) = _client(handler).campaigns(with_rules=False)
    assert c.source == "whop_bounty"
    assert c.brand == "BrandCo"
    assert c.reward_model == "per_submission"
    assert c.reward_amount == 50.0
    assert c.budget_remaining == 800.0  # budget - paid out
    assert c.spots_remaining == 16
    assert c.unresolved == 3


def test_campaigns_with_rules_fetches_description():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bounties/bnty_1"):
            return httpx.Response(200, json=_bounty(1, description="Use #brand. 30s minimum."))
        return httpx.Response(200, json={"data": [_bounty(1)], "page_info": {}})

    (c,) = _client(handler).campaigns(with_rules=True)
    assert "#brand" in c.rules_text


def test_detail_failure_keeps_campaign_without_rules():
    def handler(request: httpx.Request) -> httpx.Response:
        if "bnty_1" in request.url.path:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"data": [_bounty(1)], "page_info": {}})

    (c,) = _client(handler).campaigns(with_rules=True)
    assert c.id == "bnty_1" and c.rules_text == ""


# -- legacy /bounties fallback (production 404s /workforce/bounties, 2026-08) --


def _legacy_bounty(i, status="published", **over):
    raw = {
        "id": f"bnty_{i}", "bounty_type": "workforce",
        "title": f"Legacy campaign {i}", "status": status, "currency": "usd",
        "description": "Use #brand. At least 30 seconds.",
        "total_available": 800.0, "total_paid": 200.0, "vote_threshold": 1,
        "created_at": "2026-08-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z",
    }
    raw.update(over)
    return raw


def _fallback_handler(requests=None):
    """404 the workforce surface like production; serve legacy /bounties."""

    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if "/workforce/bounties" in request.url.path:
            return httpx.Response(404, text=json.dumps({"error": {
                "type": "not_found", "message": "Unrecognized request URL"}}))
        assert request.url.path.endswith("/bounties")
        return httpx.Response(200, json={"data": [
            _legacy_bounty(1), _legacy_bounty(2, status="archived"),
        ], "page_info": {}})

    return handler


def test_fallback_to_legacy_bounties_on_404():
    requests = []
    items = _client(_fallback_handler(requests)).list_bounties(status="open")
    assert [i["id"] for i in items] == ["bnty_1", "bnty_2"]
    # canonical status vocabulary translated to the legacy surface's
    assert requests[1].url.params["status"] == "published"
    assert all(r.method == "GET" for r in requests)


def test_legacy_translation():
    (raw, second) = _client(_fallback_handler()).list_bounties()
    assert raw["status"] == "open" and second["status"] == "closed"
    assert raw["budget_amount"] == 1000.0        # available + paid
    assert raw["gross_paid_out_amount"] == 200.0
    assert raw["gross_reward_amount"] == 0.0     # not exposed by this surface
    assert "business_goal_type" not in raw       # key absent, not empty


def test_legacy_campaigns_skip_goal_filter_and_use_inline_rules():
    requests = []
    campaigns = _client(_fallback_handler(requests)).campaigns(with_rules=True)
    # goal filter must not drop legacy items (no goal key to filter on),
    # and the inline description means no per-bounty detail fetches
    assert [c.id for c in campaigns] == ["bnty_1", "bnty_2"]
    assert campaigns[0].rules_text.startswith("Use #brand")
    assert campaigns[0].budget_remaining == 800.0
    assert len(requests) == 2  # workforce 404 + one legacy list, nothing else


def test_non_404_errors_do_not_fall_back():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad key")

    with pytest.raises(WhopError, match="401"):
        _client(handler).list_bounties()


def test_unknown_reward_scores_neutral_not_zero():
    from clipengine.campaigns.models import Campaign
    from clipengine.campaigns.score import score_campaign

    legacy = Campaign(id="bnty_1", source="whop_bounty", title="Legacy",
                      status="open", reward_amount=0.0, budget_total=1000.0,
                      budget_remaining=800.0)
    scored = score_campaign(legacy)
    assert scored.score > 0
    assert scored.breakdown["rate"] == 1.0


def test_payouts_requires_exactly_one_owner():
    client = _client(lambda r: httpx.Response(200, json={"data": []}))
    with pytest.raises(WhopError, match="exactly one"):
        client.payouts()
    with pytest.raises(WhopError, match="exactly one"):
        client.payouts(user_id="user_1", account_id="biz_1")


def test_payouts_paginates_read_only():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path.endswith("/payouts")
        if request.url.params.get("after"):
            return httpx.Response(200, json={"data": [
                {"id": "pay_2", "amount": 10.0, "status": "completed"}
            ], "page_info": {}})
        return httpx.Response(200, json={"data": [
            {"id": "pay_1", "amount": 25.0, "status": "completed"}
        ], "page_info": {"end_cursor": "c1"}})

    payouts = _client(handler).payouts(user_id="user_1")
    assert [p["id"] for p in payouts] == ["pay_1", "pay_2"]
    assert requests[0].url.params["user_id"] == "user_1"
    assert all(r.method == "GET" for r in requests)


def test_ledger_account_fetch():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/ledger_accounts/ldgr_1")
        return httpx.Response(200, json={"id": "ldgr_1", "balance": {
            "balance": 120.5, "pending_balance": 30.0, "currency": "usd"}})

    account = _client(handler).ledger_account("ldgr_1")
    assert account["balance"]["balance"] == 120.5


def test_http_error_raises_whop_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=json.dumps({"error": "bad key"}))

    with pytest.raises(WhopError, match="401"):
        _client(handler).list_bounties()
