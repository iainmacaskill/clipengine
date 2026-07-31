from clipengine.config import EditConfig
from clipengine.edit.ffmpeg import escape_drawtext, vertical_graph
from clipengine.models import FacecamRegion, SourceVideo
from clipengine.pipeline import credit_text_for

SRC = SourceVideo(path="v.mp4", width=1920, height=1080, duration=60.0)
CAM = FacecamRegion(24, 24, 420, 236)


def test_escape_drawtext():
    assert escape_drawtext("clip: twitch.tv/x") == "clip\\: twitch.tv/x"
    assert escape_drawtext("100% Bob's") == "100\\% Bob\\'s"
    assert escape_drawtext("a\\b") == "a\\\\b"


def test_graph_without_credit_has_no_drawtext():
    graph = vertical_graph(SRC, CAM, EditConfig())
    assert "drawtext" not in graph
    assert graph.endswith("[v]")


def test_graph_with_credit_burns_text_below_facecam():
    cfg = EditConfig()
    graph = vertical_graph(SRC, CAM, cfg, credit_text="clip: twitch.tv/nl")
    assert "drawtext=text='clip\\: twitch.tv/nl'" in graph
    assert f"y={cfg.facecam_tile_height + 14}" in graph
    assert graph.endswith("[v]")


def test_graph_credit_text_is_escaped():
    graph = vertical_graph(SRC, CAM, EditConfig(), credit_text="Bob's 100%: clips")
    assert "Bob\\'s 100\\%\\: clips" in graph


def test_credit_text_for_prefers_roster_format():
    assert credit_text_for("NL", "follow @NL on twitch") == "follow @NL on twitch"
    assert credit_text_for("SomeStreamer", "") == "clip: twitch.tv/somestreamer"
    assert credit_text_for("x", "   ") == "clip: twitch.tv/x"


def test_render_cli_requires_credit_choice(tmp_path, capsys):
    from clipengine import cli

    rc = cli.main(
        ["render", "v.mp4", "--start", "0", "--end", "5", "-o", str(tmp_path / "o.mp4")]
    )
    assert rc == 1
    assert "credit required" in capsys.readouterr().err
