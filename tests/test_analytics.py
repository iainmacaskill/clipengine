from datetime import datetime, timezone

import httpx

from clipengine import analytics
from clipengine.analytics import StatsStore, account_totals, report, sync, write_csv
from clipengine.publish.scheduler import Queue, ScheduleRules

UTC = timezone.utc
RULES = ScheduleRules(windows=["00:00-23:45"], min_spacing_hours=0.0, daily_cap=99, tz="UTC")


def _dt(hour, minute=0):
    return datetime(2026, 8, 1, hour, minute, tzinfo=UTC)


def _published_queue(tmp_path, posts):
    q = Queue(str(tmp_path / "q.db"))
    for platform, account, title, ext_id in posts:
        p = q.add(platform, account, "v.mp4", title, RULES, now=_dt(1))
        if ext_id:
            q.mark_published(p.id, ext_id, now=_dt(2))
    return q


def test_store_snapshots_and_latest(tmp_path):
    with StatsStore(str(tmp_path / "s.db")) as store:
        store.record("youtube", "V1", {"views": 10, "likes": 1}, fetched_at=_dt(3))
        store.record("youtube", "V1", {"views": 250, "likes": 20}, fetched_at=_dt(9))
        latest = store.latest("youtube", "V1")
        assert latest.views == 250
        history = store.history("youtube", "V1")
        assert [s.views for s in history] == [10, 250]  # velocity data preserved


def test_sync_snapshots_published_posts_only(tmp_path):
    q = _published_queue(
        tmp_path,
        [
            ("youtube", "c1", "hit", "V1"),
            ("youtube", "c1", "unpublished", None),
            ("tiktok", "t1", "tt clip", "T1"),
        ],
    )
    store = StatsStore(str(tmp_path / "s.db"))
    fetched = {}

    def yt_fetch(ids):
        fetched["youtube"] = ids
        return {"V1": {"views": 100, "likes": 5}}

    count = sync(q, store, {"youtube": yt_fetch}, now=_dt(3))
    assert count == 1
    assert fetched["youtube"] == ["V1"]  # unpublished + other-platform excluded
    assert store.latest("youtube", "V1").views == 100
    assert store.latest("tiktok", "T1") is None  # no fetcher -> skipped


def test_report_joins_and_sorts_by_views(tmp_path):
    q = _published_queue(
        tmp_path, [("youtube", "c1", "small", "V1"), ("youtube", "c1", "big", "V2")]
    )
    store = StatsStore(str(tmp_path / "s.db"))
    store.record("youtube", "V1", {"views": 10}, fetched_at=_dt(3))
    store.record("youtube", "V2", {"views": 9000, "likes": 400}, fetched_at=_dt(3))
    rows = report(q, store)
    assert [r.title for r in rows] == ["big", "small"]
    assert rows[0].views == 9000 and rows[0].account == "c1"


def test_report_includes_unsynced_as_zero(tmp_path):
    q = _published_queue(tmp_path, [("youtube", "c1", "fresh", "V9")])
    rows = report(q, StatsStore(str(tmp_path / "s.db")))
    assert rows[0].views == 0


def test_account_totals(tmp_path):
    q = _published_queue(
        tmp_path,
        [
            ("youtube", "c1", "a", "V1"),
            ("youtube", "c1", "b", "V2"),
            ("tiktok", "t1", "c", "T1"),
        ],
    )
    store = StatsStore(str(tmp_path / "s.db"))
    store.record("youtube", "V1", {"views": 100, "likes": 10}, fetched_at=_dt(3))
    store.record("youtube", "V2", {"views": 50, "likes": 5}, fetched_at=_dt(3))
    store.record("tiktok", "T1", {"views": 7}, fetched_at=_dt(3))
    totals = account_totals(report(q, store))
    assert totals[("youtube", "c1")] == {"posts": 2, "views": 150, "likes": 15}
    assert totals[("tiktok", "t1")]["views"] == 7


def test_write_csv(tmp_path):
    q = _published_queue(tmp_path, [("youtube", "c1", "a", "V1")])
    store = StatsStore(str(tmp_path / "s.db"))
    store.record("youtube", "V1", {"views": 3}, fetched_at=_dt(3))
    path = str(tmp_path / "out.csv")
    write_csv(report(q, store), path)
    lines = open(path).read().strip().splitlines()
    assert lines[0].startswith("post_id,platform")
    assert ",youtube,c1,a,V1," in lines[1]


# -- platform stats fetchers ----------------------------------------------


def _fresh_store(tmp_path, name):
    import time

    from clipengine.publish.tokens import TokenSet, TokenStore

    path = str(tmp_path / name)
    TokenStore(path).save(TokenSet("tok", "ref", time.time() + 3600))
    return path


def test_youtube_stats_fetch(tmp_path):
    from clipengine.publish.youtube import YouTubeClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["part"] == "statistics"
        assert request.url.params["id"] == "V1,V2"
        return httpx.Response(
            200,
            json={
                "items": [
                    {"id": "V1", "statistics": {"viewCount": "120", "likeCount": "8"}},
                    {"id": "V2", "statistics": {"viewCount": "3"}},
                ]
            },
        )

    client = YouTubeClient(
        "cid", "cs", _fresh_store(tmp_path, "yt.json"),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    stats = client.stats(["V1", "V2"])
    assert stats["V1"] == {"views": 120, "likes": 8, "comments": 0, "shares": 0}
    assert stats["V2"]["views"] == 3


def test_tiktok_stats_fetch(tmp_path):
    from clipengine.publish.tiktok import TikTokClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert "view_count" in request.url.params["fields"]
        return httpx.Response(
            200,
            json={
                "data": {
                    "videos": [
                        {"id": 111, "view_count": 900, "like_count": 40, "share_count": 3}
                    ]
                }
            },
        )

    client = TikTokClient(
        "k", "s", _fresh_store(tmp_path, "tt.json"),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_s=0,
    )
    stats = client.video_stats(["111"])
    assert stats["111"] == {"views": 900, "likes": 40, "comments": 0, "shares": 3}


def test_tiktok_publish_captures_public_video_id(tmp_path):
    from clipengine.publish.tiktok import PostRequest, TikTokClient

    video = tmp_path / "c.mp4"
    video.write_bytes(b"x")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/video/init/"):
            return httpx.Response(
                200, json={"data": {"publish_id": "PUB1", "upload_url": "https://up.example/u"}}
            )
        if "up.example" in url:
            return httpx.Response(200)
        return httpx.Response(
            200,
            json={
                "data": {
                    "status": "PUBLISH_COMPLETE",
                    "publicaly_available_post_id": [7345678901234567890],
                }
            },
        )

    client = TikTokClient(
        "k", "s", _fresh_store(tmp_path, "tt2.json"),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_s=0,
    )
    assert client.post(PostRequest(str(video), "t")) == "7345678901234567890"
