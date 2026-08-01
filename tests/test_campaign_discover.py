import pytest

from clipengine.campaigns.discover import parse_discover

# -- fixtures: the two page shapes the parser must survive ------------------

RSC_PAGE = """<html><body><div id="app"></div>
<script>self.__next_f.push([1,"{\\"campaigns\\":[
{\\"title\\":\\"Roobet Clips\\",\\"rewardRate\\":1.0,\\"totalBudget\\":250000,
\\"paidOut\\":100000,\\"platforms\\":[\\"tiktok\\",\\"instagram\\"],\\"route\\":\\"roobet-clips\\"},
{\\"title\\":\\"CoD MW4 Moments\\",\\"rewardRate\\":1.5,\\"totalBudget\\":120000,
\\"paidOut\\":30000,\\"platforms\\":[\\"tiktok\\",\\"youtube\\"],\\"route\\":\\"cod-mw4\\"}
]}"])</script></body></html>"""

TEXT_PAGE = """<html><body>
<div class="card"><h3>Pacinos Hair</h3><span>Clipping</span>
<span>$1 / 1K</span><span>$12,500 of $50,000 paid</span>
<span>TikTok</span><span>Instagram</span></div>
<div class="card"><h3>Boxabl Homes</h3><span>UGC</span>
<span>$0.50 per 1,000 views</span><span>$40K of $85K paid</span>
<span>YouTube</span><span>X</span></div>
<div class="card"><h3>Tiny Outlier</h3>
<span>$15 / 1K</span><span>$900 of $1,000 paid</span><span>TikTok</span></div>
</body></html>"""


def test_parses_embedded_json_campaigns():
    found = {d.title: d for d in parse_discover(RSC_PAGE)}
    assert set(found) == {"Roobet Clips", "CoD MW4 Moments"}
    roobet = found["Roobet Clips"]
    assert roobet.rate == 1.0
    assert roobet.budget_total == 250000
    assert roobet.budget_remaining == 150000  # total - paid
    assert roobet.platforms == ["tiktok", "instagram"]
    assert roobet.url == "https://whop.com/roobet-clips"


def test_parses_visible_text_cards():
    found = {d.title: d for d in parse_discover(TEXT_PAGE)}
    assert set(found) == {"Pacinos Hair", "Boxabl Homes", "Tiny Outlier"}
    pacinos = found["Pacinos Hair"]
    assert pacinos.rate == 1.0
    assert (pacinos.budget_total, pacinos.budget_remaining) == (50000, 37500)
    assert pacinos.platforms == ["tiktok", "instagram"]
    boxabl = found["Boxabl Homes"]
    assert boxabl.rate == 0.5
    assert boxabl.budget_total == 85000  # K suffix handled
    assert boxabl.platforms == ["youtube", "x"]  # bare X chip counts, substrings don't


def test_unparseable_page_degrades_to_empty():
    assert parse_discover("<html><body><h1>Something else</h1></body></html>") == []
    assert parse_discover("") == []


def test_to_campaign_normalisation():
    (c,) = [d.to_campaign() for d in parse_discover(TEXT_PAGE)
            if d.title == "Pacinos Hair"]
    assert c.id == "disc:pacinos-hair"
    assert c.reward_model == "cpm" and c.reward_amount == 1.0
    assert c.budget_remaining == 37500
    assert c.open


# -- CLI ---------------------------------------------------------------------


@pytest.fixture
def env(tmp_path):
    cfg = tmp_path / "cfg.toml"
    cfg.write_text(f'[campaigns]\ncampaigns_db = "{tmp_path / "campaigns.db"}"\n')
    page = tmp_path / "page.html"
    page.write_text(TEXT_PAGE)
    return str(cfg), str(page)


def _run(env, *argv):
    from clipengine import cli

    return cli.main(["--config", env[0], "campaigns", "discover", "--file", env[1], *argv])


def test_cli_ranks_by_score_by_default(env, capsys):
    assert _run(env) == 0
    out = capsys.readouterr().out.splitlines()
    # big-budget $1/1k campaign should outrank the tiny $15/1k outlier on EV
    assert out[0].endswith("Pacinos Hair")
    assert any("Tiny Outlier" in ln for ln in out)


def test_cli_sort_rate_puts_outlier_first(env, capsys):
    assert _run(env, "--sort", "rate") == 0
    assert capsys.readouterr().out.splitlines()[0].endswith("Tiny Outlier")


def test_cli_min_cpm_filters_and_reports(env, capsys):
    assert _run(env, "--min-cpm", "0.9") == 0
    captured = capsys.readouterr()
    assert "Boxabl" not in captured.out
    assert "below --min-cpm" in captured.err


def test_cli_add_stores_and_rules_attach_flows(env, tmp_path, capsys):
    from clipengine import cli
    from clipengine.campaigns.store import CampaignStore

    assert _run(env, "--top", "2", "--add") == 0
    out = capsys.readouterr().out
    assert "stored 2 campaign(s), 2 new" in out
    with CampaignStore(str(tmp_path / "campaigns.db")) as store:
        assert store.get("disc:pacinos-hair") is not None

    brief = tmp_path / "brief.txt"
    brief.write_text("Must include #Pacinos. At least 30 seconds.")
    rc = cli.main(["--config", env[0], "campaigns", "rules",
                   "disc:pacinos-hair", "--attach", str(brief)])
    assert rc == 0
    assert "#Pacinos" in capsys.readouterr().out
    with CampaignStore(str(tmp_path / "campaigns.db")) as store:
        assert "#Pacinos" in store.get("disc:pacinos-hair").rules_text


def test_cli_unparseable_page_exits_1(env, tmp_path, capsys):
    from clipengine import cli

    bad = tmp_path / "bad.html"
    bad.write_text("<html><body>nothing here</body></html>")
    rc = cli.main(["--config", env[0], "campaigns", "discover", "--file", str(bad)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "--browser" in err          # points at the client-rendered fix
    assert "rate texts (visible): 0" in err  # diagnostics printed automatically