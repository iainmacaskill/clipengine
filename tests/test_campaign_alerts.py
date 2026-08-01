import httpx

from clipengine.campaigns import alerts
from clipengine.campaigns.models import Campaign
from clipengine.campaigns.score import score_campaign


def _scored(**over):
    base = dict(
        id="bnty_1", source="whop_bounty", title="Clip campaign", brand="BrandCo",
        status="open", reward_model="per_submission", reward_amount=50.0,
        budget_total=1000.0, budget_remaining=800.0, currency="usd",
    )
    base.update(over)
    return score_campaign(Campaign(**base))


def test_notify_posts_discord_compatible_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = request.read()
        return httpx.Response(204)

    ok = alerts.notify(
        "https://discord.test/webhook", [_scored()],
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert ok
    body = captured["json"].decode()
    assert '"content"' in body
    assert "Clip campaign" in body and "BrandCo" in body


def test_cpm_and_submission_rewards_formatted():
    text = alerts.format_alert([
        _scored(),
        _scored(id="manual:x", source="manual", reward_model="cpm", reward_amount=2.0),
    ])
    assert "50 usd/submission" in text
    assert "2 usd/1k views" in text


def test_notify_failure_returns_false():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert not alerts.notify(
        "https://discord.test/webhook", [_scored()],
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_notify_skips_empty():
    assert not alerts.notify("https://discord.test/webhook", [])
    assert not alerts.notify("", [_scored()])
