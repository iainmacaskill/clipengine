import pytest

from clipengine.ingest import vod
from clipengine.ingest.vod import build_opts, download_vod, normalise_vod_url


def test_normalise_bare_id():
    assert normalise_vod_url("2274633451") == "https://www.twitch.tv/videos/2274633451"


def test_normalise_url_forms():
    for form in [
        "https://www.twitch.tv/videos/123?t=1h2m",
        "twitch.tv/videos/123",
        "http://m.twitch.tv/videos/123",
    ]:
        assert normalise_vod_url(form) == "https://www.twitch.tv/videos/123"


def test_normalise_rejects_non_vod():
    with pytest.raises(ValueError):
        normalise_vod_url("https://www.twitch.tv/somestreamer")


def test_build_opts_quality_cap_and_output():
    opts = build_opts("/tmp/x.mp4", max_height=720)
    assert opts["outtmpl"]["default"] == "/tmp/x.mp4"
    assert "height<=720" in opts["format"]
    assert "download_ranges" not in opts


def test_build_opts_range_download():
    opts = build_opts("/tmp/x.mp4", start=100.0, end=200.0)
    assert opts["force_keyframes_at_cuts"] is True
    ranges = list(opts["download_ranges"]({"chapters": []}, None))
    assert [(r["start_time"], r["end_time"]) for r in ranges] == [(100.0, 200.0)]


def test_build_opts_cookies_passthrough():
    opts = build_opts("/tmp/x.mp4", cookies_file="/tmp/cookies.txt")
    assert opts["cookiefile"] == "/tmp/cookies.txt"


def test_download_vod_invokes_ytdlp_with_url(tmp_path, monkeypatch):
    calls = {}

    class FakeYDL:
        def __init__(self, opts):
            calls["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def download(self, urls):
            calls["urls"] = urls
            # simulate yt-dlp writing the file
            open(calls["opts"]["outtmpl"]["default"], "w").write("x")
            return 0

    import yt_dlp

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    dst = str(tmp_path / "vod.mp4")
    out = download_vod("123", dst)
    assert out == dst
    assert calls["urls"] == ["https://www.twitch.tv/videos/123"]


def test_download_vod_raises_on_failure(tmp_path, monkeypatch):
    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def download(self, urls):
            return 1

    import yt_dlp

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    with pytest.raises(RuntimeError, match="download failed"):
        download_vod("123", str(tmp_path / "vod.mp4"))
