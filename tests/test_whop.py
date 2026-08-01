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


def test_http_error_raises_whop_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=json.dumps({"error": "bad key"}))

    with pytest.raises(WhopError, match="401"):
        _client(handler).list_bounties()
