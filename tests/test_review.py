import json

import pytest

from clipengine.review import ReviewQueue


def _manifest(tmp_path, items):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(items))
    return str(p)


def _item(path, status="rendered", **kw):
    d = {
        "index": 1, "start": 100.0, "end": 175.0, "score": 2.5,
        "signals": {"chat_velocity": 1.2}, "streamer": "nl",
        "credit": "clip: twitch.tv/nl", "path": path, "status": status,
    }
    d.update(kw)
    return d


@pytest.fixture
def rq(tmp_path):
    with ReviewQueue(str(tmp_path / "review.db")) as q:
        yield q


def test_import_adds_rendered_skips_failed_and_dupes(rq, tmp_path):
    m = _manifest(
        tmp_path,
        [
            _item("a.mp4"),
            _item("b.mp4", status="failed", error="boom"),
            _item("a.mp4"),  # duplicate path
        ],
    )
    added, skipped = rq.import_manifest(m)
    assert (added, skipped) == (1, 2)
    clips = rq.list(status="pending")
    assert len(clips) == 1 and clips[0].streamer == "nl"


def test_reimport_is_idempotent(rq, tmp_path):
    m = _manifest(tmp_path, [_item("a.mp4")])
    rq.import_manifest(m)
    added, skipped = rq.import_manifest(m)
    assert (added, skipped) == (0, 1)


def test_approve_requires_title(rq, tmp_path):
    rq.import_manifest(_manifest(tmp_path, [_item("a.mp4")]))
    with pytest.raises(ValueError, match="real title"):
        rq.approve(1, "   ")
    clip = rq.approve(1, "INSANE clutch moment")
    assert clip.status == "approved" and clip.title == "INSANE clutch moment"


def test_reject_requires_reason(rq, tmp_path):
    rq.import_manifest(_manifest(tmp_path, [_item("a.mp4")]))
    with pytest.raises(ValueError, match="reason"):
        rq.reject(1, "")
    clip = rq.reject(1, "cut too early")
    assert clip.status == "rejected" and clip.reason == "cut too early"


def test_double_decision_rejected(rq, tmp_path):
    rq.import_manifest(_manifest(tmp_path, [_item("a.mp4")]))
    rq.approve(1, "title")
    with pytest.raises(ValueError, match="already approved"):
        rq.reject(1, "changed my mind")


def test_stats_pass_rate_and_reasons(rq, tmp_path):
    rq.import_manifest(
        _manifest(tmp_path, [_item(f"{i}.mp4") for i in range(5)])
    )
    rq.approve(1, "one")
    rq.approve(2, "two")
    rq.reject(3, "Not Funny")
    rq.reject(4, "not funny")
    s = rq.stats()
    assert s["pending"] == 1
    assert s["approved"] == 2 and s["rejected"] == 2
    assert s["pass_rate"] == 0.5
    assert s["rejection_reasons"] == {"not funny": 2}  # case-normalised


def test_stats_empty(rq):
    assert rq.stats()["pass_rate"] is None


def test_cli_approve_enqueues(tmp_path):
    from clipengine import cli
    from clipengine.publish.scheduler import Queue

    manifest = _manifest(tmp_path, [_item("clip_a.mp4")])
    cfg_file = tmp_path / "cfg.toml"
    cfg_file.write_text(
        f'review_db = "{tmp_path}/review.db"\n'
        f'[schedule]\nqueue_db = "{tmp_path}/q.db"\n'
        f'windows = ["00:00-23:45"]\nmin_spacing_hours = 0.5\ndaily_cap = 10\n'
    )
    assert cli.main(["--config", str(cfg_file), "review", "import", manifest]) == 0
    assert (
        cli.main(
            [
                "--config", str(cfg_file), "review", "approve", "1",
                "--title", "clutch", "--queue-platform", "youtube",
                "--account", "chan1", "--privacy", "unlisted",
            ]
        )
        == 0
    )
    with Queue(str(tmp_path / "q.db")) as q:
        posts = q.list()
    assert len(posts) == 1
    assert posts[0].title == "clutch" and posts[0].privacy == "unlisted"
    with ReviewQueue(str(tmp_path / "review.db")) as rq:
        assert rq.get(1).queued_post_id == posts[0].id
