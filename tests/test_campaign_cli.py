import httpx
import pytest

from clipengine import cli


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Config TOML pointing the campaign store at a temp DB."""
    cfg = tmp_path / "cfg.toml"
    cfg.write_text(
        f'[campaigns]\ncampaigns_db = "{tmp_path / "campaigns.db"}"\n'
        'familiarity = { valorant = 1.2 }\n'
    )
    monkeypatch.delenv("CLIPENGINE_WHOP_API_KEY", raising=False)
    monkeypatch.delenv("WHOP_API_KEY", raising=False)
    return str(cfg)


def _run(env, *argv):
    return cli.main(["--config", env, "campaigns", *argv])


def test_add_list_show_roundtrip(env, capsys):
    rc = _run(env, "add", "--title", "Valorant Neon clips", "--cpm", "2",
              "--budget", "5000", "--brand", "Neon",
              "--platforms", "tiktok,youtube",
              "--rules", "Must include #NeonClips. At least 30 seconds. No AI voiceovers.")
    assert rc == 0
    assert "added manual:valorant-neon-clips" in capsys.readouterr().out

    assert _run(env, "list") == 0
    out = capsys.readouterr().out
    assert "manual:valorant-neon-clips" in out and "2/1k" in out

    assert _run(env, "show", "manual:valorant-neon-clips") == 0
    out = capsys.readouterr().out
    assert "per 1k views" in out
    assert "hashtags: #NeonClips" in out
    assert "duration: 30s" in out
    assert "familiarity" in out  # score breakdown visible


def test_rules_from_file(env, tmp_path, capsys):
    rules = tmp_path / "rules.txt"
    rules.write_text("Use #GG and tag @brand. Post to TikTok. Max 60 seconds.")
    assert _run(env, "rules", "--file", str(rules)) == 0
    out = capsys.readouterr().out
    assert "#GG" in out and "@brand" in out and "tiktok" in out


def test_show_unknown_campaign_fails(env, capsys):
    assert _run(env, "show", "bnty_nope") == 1


def test_sync_without_api_key_exits_2(env, capsys):
    assert _run(env, "sync") == 2
    assert "API key" in capsys.readouterr().err


def test_sync_stores_and_reports_new(env, monkeypatch, capsys):
    from clipengine.campaigns import whop

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("bnty_1"):
            return httpx.Response(200, json={"description": "Use #brand"})
        return httpx.Response(200, json={"data": [{
            "id": "bnty_1", "title": "Big clip push", "status": "open",
            "business_goal_type": "clipping", "currency": "usd",
            "budget_amount": 2000.0, "gross_reward_amount": 40.0,
            "gross_paid_out_amount": 0.0, "spots_remaining": 50,
            "unresolved_submissions_count": 0,
            "created_at": "2026-08-01T00:00:00Z",
            "funding_account": {"id": "biz_1", "title": "BrandCo"},
        }], "page_info": {}})

    monkeypatch.setenv("CLIPENGINE_WHOP_API_KEY", "k")
    real_init = whop.WhopClient.__init__

    def patched(self, api_key, client=None, base_url=whop.BASE_URL):
        real_init(self, api_key,
                  client=httpx.Client(transport=httpx.MockTransport(handler)),
                  base_url=base_url)

    monkeypatch.setattr(whop.WhopClient, "__init__", patched)
    assert _run(env, "sync") == 0
    out = capsys.readouterr().out
    assert "synced 1 campaign(s), 1 new" in out
    assert "Big clip push" in out
    # second sync: nothing new
    assert _run(env, "sync") == 0
    assert "1 campaign(s), 0 new" in capsys.readouterr().out
