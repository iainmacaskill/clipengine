import pytest

from clipengine.roster import Roster


@pytest.fixture
def roster(tmp_path):
    with Roster(str(tmp_path / "roster.db")) as r:
        yield r


def _csv(tmp_path, text):
    p = tmp_path / "roster.csv"
    p.write_text(text)
    return str(p)


def test_import_full_columns(roster, tmp_path):
    path = _csv(
        tmp_path,
        "login,source,evidence,credit,exclusions,notes\n"
        "StreamerA,published_policy,https://a.tv/policy,clip: twitch.tv/a,,\n"
        "streamerb,opt_in,consent#1,follow @b,no sponsor segments,via email\n",
    )
    imported, errors = roster.import_csv(path)
    assert len(imported) == 2 and errors == []
    b = roster.require("streamerb")
    assert b.source == "opt_in" and b.exclusions == "no sponsor segments"
    assert roster.require("streamera").allowed  # login lowercased


def test_import_minimal_columns_uses_default_source(roster, tmp_path):
    path = _csv(tmp_path, "login,evidence\nx,https://x.tv/policy\n")
    imported, errors = roster.import_csv(path, default_source="published_policy")
    assert errors == [] and imported[0].source == "published_policy"


def test_import_bad_rows_skipped_not_fatal(roster, tmp_path):
    path = _csv(
        tmp_path,
        "login,source,evidence\n"
        "good,published_policy,https://g.tv/p\n"
        "noevidence,published_policy,\n"
        "badsource,verbal_maybe,https://b.tv/p\n"
        "alsogood,opt_in,consent#2\n",
    )
    imported, errors = roster.import_csv(path)
    assert [e.login for e in imported] == ["good", "alsogood"]
    assert len(errors) == 2
    assert "row 3" in errors[0] and "evidence required" in errors[0]
    assert "row 4" in errors[1] and "source must be" in errors[1]


def test_import_missing_header_raises(roster, tmp_path):
    path = _csv(tmp_path, "name,url\nx,y\n")
    with pytest.raises(ValueError, match="header"):
        roster.import_csv(path)


def test_import_upserts_existing(roster, tmp_path):
    roster.add("x", source="opt_in", evidence="old#1")
    roster.revoke("x")
    path = _csv(tmp_path, "login,evidence\nx,https://x.tv/new-policy\n")
    imported, errors = roster.import_csv(path)
    assert errors == []
    entry = roster.require("x")  # re-granted
    assert entry.evidence == "https://x.tv/new-policy"


def test_export_roundtrip(roster, tmp_path):
    roster.add("a", source="published_policy", evidence="https://a/p", credit="clip: a")
    roster.add("b", source="opt_in", evidence="c#1")
    roster.revoke("b", reason="asked")
    out = str(tmp_path / "export.csv")
    assert roster.export_csv(out) == 2
    with Roster(str(tmp_path / "other.db")) as other:
        imported, errors = other.import_csv(out)
        # revoked entries re-import as allowed grants - export is a backup,
        # import is an intentional (re-)grant action
        assert errors == [] and len(imported) == 2
        assert other.require("a").credit == "clip: a"


def test_cli_import_reports_and_fails_on_errors(tmp_path, capsys):
    from clipengine import cli

    cfg_file = tmp_path / "cfg.toml"
    cfg_file.write_text(f'roster_db = "{tmp_path}/roster.db"\n')
    path = _csv(tmp_path, "login,evidence\ngood,https://g.tv/p\nbad,\n")
    rc = cli.main(["--config", str(cfg_file), "roster", "import", str(path)])
    out = capsys.readouterr()
    assert rc == 1  # errors present
    assert "1 imported, 1 skipped" in out.out
    assert "roster now has 1 allowed streamer" in out.out
    assert "row 3" in out.err
