import pytest

from clipengine.roster import PermissionError_, Roster


@pytest.fixture
def roster(tmp_path):
    with Roster(str(tmp_path / "roster.db")) as r:
        yield r


def test_add_and_require(roster):
    roster.add("SomeStreamer", source="published_policy", evidence="https://x.tv/clip-policy")
    entry = roster.require("somestreamer")  # login normalised to lowercase
    assert entry.allowed and entry.source == "published_policy"


def test_unknown_streamer_refused(roster):
    with pytest.raises(PermissionError_, match="not on the permission roster"):
        roster.require("nobody")


def test_revoke_takes_effect_immediately(roster):
    roster.add("a", source="opt_in", evidence="consent#42")
    roster.revoke("a", reason="asked to stop")
    with pytest.raises(PermissionError_, match="revoked"):
        roster.require("a")
    entry = roster.get("a")
    assert entry.revoked_at is not None and "asked to stop" in entry.notes


def test_regrant_after_revoke(roster):
    roster.add("a", source="opt_in", evidence="consent#42")
    roster.revoke("a")
    roster.add("a", source="licence", evidence="contract#7")
    entry = roster.require("a")
    assert entry.allowed and entry.source == "licence" and entry.revoked_at is None


def test_evidence_is_mandatory(roster):
    with pytest.raises(ValueError, match="evidence required"):
        roster.add("a", source="opt_in", evidence="   ")


def test_invalid_source_rejected(roster):
    with pytest.raises(ValueError, match="source must be"):
        roster.add("a", source="verbal_maybe", evidence="x")


def test_list_filters_by_status(roster):
    roster.add("a", source="opt_in", evidence="c#1")
    roster.add("b", source="opt_in", evidence="c#2")
    roster.revoke("b")
    assert [e.login for e in roster.list(status="allowed")] == ["a"]
    assert [e.login for e in roster.list(status="revoked")] == ["b"]
    assert len(roster.list()) == 2


def test_cli_gate_blocks_download_before_network(tmp_path, monkeypatch, capsys):
    """`clipengine vod` must refuse unlisted streamers before any download runs."""
    from clipengine import cli

    called = {}
    monkeypatch.setattr(
        "clipengine.ingest.vod.download_vod",
        lambda *a, **k: called.setdefault("download", True),
    )
    cfg_file = tmp_path / "cfg.toml"
    cfg_file.write_text(f'roster_db = "{tmp_path}/roster.db"\n')
    rc = cli.main(
        [
            "--config", str(cfg_file), "vod", "123",
            "--streamer", "unlisted", "-o", str(tmp_path / "v.mp4"),
        ]
    )
    assert rc == 2
    assert "not on the permission roster" in capsys.readouterr().err
    assert "download" not in called
