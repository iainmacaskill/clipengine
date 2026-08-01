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
<div class="card"><h3>Pacinos Hair</h3><span>Product</span><span>Clipping</span>
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


# verbatim line shapes from a real rendered-feed --debug run (2026-08)
SPLIT_PAGE = "\n".join([
    "0", "$2", "/1K", "Propaganda", "·", "15d", "Product",
    "Pacinos UGC Clipping | $50k Budget | $1 CPM",
    "Clip and post approved Pacinos UGC content showcasing grooming products",
    "Join Campaign", "$41,370", "/$50,000",
    "0", "$1.80", "/1K", "Imako", "·", "7d", "Product",
    "IMAKO Cosmetic Teeth — Clip-On Smile Transformations | $2.00 / 1K",
    "Get paid to clip real smile transformations on TikTok.",
    "Join Campaign", "$619", "/$2,000",
    "0", "$1.50", "/1K", "Reachify", "·", "3mo", "Slideshow",
    "DreamMe [HEALTH]",
    "Make TikTok slideshow content promoting the DreamMe GLP-1 tracking app.",
    "40% tier 1 audience reqquirement (USA,UK,CA TOP PRIORITIZED)",
    "Join Campaign", "$19,571", "/$29,500",
])


def test_split_card_layout_parses_the_live_feed():
    found = {d.title: d for d in parse_discover(SPLIT_PAGE)}
    assert set(found) == {
        "Pacinos UGC Clipping | $50k Budget | $1 CPM (Propaganda)",
        "IMAKO Cosmetic Teeth — Clip-On Smile Transformations | $2.00 / 1K (Imako)",
        "DreamMe [HEALTH] (Reachify)",
    }
    pacinos = found["Pacinos UGC Clipping | $50k Budget | $1 CPM (Propaganda)"]
    assert pacinos.rate == 2.0            # from the $2 + /1K anchor, NOT the
    assert pacinos.budget_total == 50000  # '$1 CPM' text inside the title
    assert pacinos.budget_remaining == 8630.0  # 50,000 - 41,370
    dreamme = found["DreamMe [HEALTH] (Reachify)"]
    assert dreamme.rate == 1.5
    assert dreamme.budget_remaining == 29500 - 19571
    imako = found["IMAKO Cosmetic Teeth — Clip-On Smile Transformations | $2.00 / 1K (Imako)"]
    assert imako.rate == 1.8              # the anchor wins over '$2.00 / 1K' in the title
    assert imako.budget_remaining == 2000 - 619


def test_split_cards_not_confused_by_description_rates():
    """'Get paid $1/1k Views!' description lines were the old false anchor."""
    page = "\n".join([
        "$0.50", "/1K", "ClipUp Official", "·", "9d", "Entertainment",
        "Omoggle Clipping",
        "Clip for Omoggle and their celebrity appearances!",
        "Get paid $1/1k Views! Viral template, easy campaign.",
        "Join Campaign", "$3,159", "/$12,000",
    ])
    (d,) = parse_discover(page)
    assert d.title == "Omoggle Clipping (ClipUp Official)"
    assert d.rate == 0.5                      # the anchor, not the $1 in the blurb
    assert d.budget_remaining == 12000 - 3159


def test_category_chips_are_not_titles():
    """Live-feed defect: 'Product'/'Technology' chips sat between the real
    title and the rate and were being picked as titles."""
    page = """<div><h3>Daimon X Syndicate</h3><span>Technology</span>
    <span>Clipping</span><span>$4 / 1K</span><span>$1K of $9K paid</span></div>"""
    (d,) = parse_discover(page)
    assert d.title == "Daimon X Syndicate"


def test_card_contexts_debug_view():
    from clipengine.campaigns.discover import card_contexts

    contexts = card_contexts(TEXT_PAGE)
    assert len(contexts) == 3
    assert any("Pacinos Hair" in ln for ln in contexts[0])
    assert any("$1 / 1K" in ln for ln in contexts[0])


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


def test_cli_max_cpm_drops_implausible_rates(env, tmp_path, capsys):
    from clipengine import cli

    page = tmp_path / "weird.html"
    page.write_text("\n".join([
        "$1,000", "/1K", "Authority Army", "·", "2d", "Product",
        "Carey James | Clipping Campaign", "Some blurb",
        "Join Campaign", "$720", "/$1,000",
        "0", "$2", "/1K", "Propaganda", "·", "15d", "Product",
        "Pacinos UGC Clipping", "Blurb", "Join Campaign", "$41,370", "/$50,000",
    ]))
    rc = cli.main(["--config", env[0], "campaigns", "discover", "--file", str(page)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Carey James" not in captured.out          # implausible rate dropped
    assert "Pacinos" in captured.out
    assert "mis-parsed" in captured.err
    # override keeps it
    rc = cli.main(["--config", env[0], "campaigns", "discover", "--file", str(page),
                   "--max-cpm", "2000"])
    assert "Carey James" in capsys.readouterr().out


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