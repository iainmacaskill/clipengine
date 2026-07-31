from datetime import datetime, timezone

import pytest

from clipengine.publish.scheduler import Post, Queue, ScheduleRules, next_slot, run_due

UTC = timezone.utc
RULES = ScheduleRules(
    windows=["10:00-12:00", "18:00-22:00"], min_spacing_hours=3.0, daily_cap=3, tz="UTC"
)


def _dt(day, hour, minute=0):
    return datetime(2026, 8, day, hour, minute, tzinfo=UTC)


# -- slot allocation ------------------------------------------------------


def test_slot_waits_for_window():
    # 08:00 -> first window opens 10:00
    assert next_slot(_dt(1, 8), [], RULES) == _dt(1, 10)


def test_slot_inside_window_is_immediate():
    assert next_slot(_dt(1, 10, 30), [], RULES) == _dt(1, 10, 30)


def test_slot_respects_spacing():
    # existing post at 10:00; 3h spacing pushes past the morning window into evening
    slot = next_slot(_dt(1, 10), [_dt(1, 10)], RULES)
    assert slot == _dt(1, 18)


def test_slot_respects_daily_cap():
    existing = [_dt(1, 10), _dt(1, 18), _dt(1, 21, 15)]  # cap=3 reached
    slot = next_slot(_dt(1, 9), existing, RULES)
    assert slot.date() == _dt(2, 10).date() and slot == _dt(2, 10)


def test_slot_timezone_windows():
    rules = ScheduleRules(windows=["18:00-22:00"], daily_cap=4, tz="America/New_York")
    # 21:00 UTC on Aug 1 is 17:00 in New York (EDT): window not open yet;
    # it opens 18:00 NY = 22:00 UTC
    assert next_slot(_dt(1, 21), [], rules) == _dt(1, 22)


def test_slot_saturated_raises():
    rules = ScheduleRules(windows=["10:00-10:15"], min_spacing_hours=0.0, daily_cap=1, tz="UTC")
    existing = [_dt(d, 10) for d in range(1, 16)]  # every day taken for 15 days
    with pytest.raises(RuntimeError, match="no free slot"):
        next_slot(_dt(1, 9), existing, rules)


def test_bad_window_rejected():
    with pytest.raises(ValueError):
        next_slot(_dt(1, 9), [], ScheduleRules(windows=["22:00-10:00"]))


# -- queue ----------------------------------------------------------------


@pytest.fixture
def queue(tmp_path):
    with Queue(str(tmp_path / "q.db")) as q:
        yield q


def test_add_assigns_slots_with_spacing(queue):
    now = _dt(1, 9)
    p1 = queue.add("youtube", "chan1", "a.mp4", "clip one", RULES, now=now)
    p2 = queue.add("youtube", "chan1", "b.mp4", "clip two", RULES, now=now)
    assert p1.scheduled_at == _dt(1, 10).isoformat()
    assert p2.scheduled_at == _dt(1, 18).isoformat()  # pushed by 3h spacing + window


def test_accounts_are_independent(queue):
    now = _dt(1, 9)
    p1 = queue.add("youtube", "chan1", "a.mp4", "one", RULES, now=now)
    p2 = queue.add("youtube", "chan2", "b.mp4", "two", RULES, now=now)
    assert p1.scheduled_at == p2.scheduled_at  # no cross-account interference


def test_cancel_frees_slot(queue):
    now = _dt(1, 9)
    p1 = queue.add("youtube", "chan1", "a.mp4", "one", RULES, now=now)
    queue.cancel(p1.id)
    p2 = queue.add("youtube", "chan1", "b.mp4", "two", RULES, now=now)
    assert p2.scheduled_at == _dt(1, 10).isoformat()  # cancelled slot reused


def test_cancel_published_rejected(queue):
    p = queue.add("youtube", "c", "a.mp4", "t", RULES, now=_dt(1, 9))
    queue.mark_published(p.id, "VID1")
    with pytest.raises(ValueError, match="not scheduled"):
        queue.cancel(p.id)


def test_due_only_returns_past_scheduled(queue):
    queue.add("youtube", "c", "a.mp4", "t", RULES, now=_dt(1, 9))  # slot 10:00
    assert queue.due(now=_dt(1, 9, 30)) == []
    assert [p.title for p in queue.due(now=_dt(1, 10))] == ["t"]


# -- run_due --------------------------------------------------------------


def test_run_due_publishes_and_records(queue):
    p = queue.add("youtube", "c", "a.mp4", "t", RULES, now=_dt(1, 9))
    results = run_due(
        queue,
        {"youtube": lambda post: "VID9"},
        screen=lambda path: True,
        now=_dt(1, 10),
    )
    assert results[0][1] == "VID9"
    stored = queue.get(p.id)
    assert stored.status == "published" and stored.external_id == "VID9"


def test_run_due_music_flagged_fails_attempt(queue):
    p = queue.add("tiktok", "c", "a.mp4", "t", RULES, now=_dt(1, 9))
    results = run_due(
        queue,
        {"tiktok": lambda post: "X"},
        screen=lambda path: False,
        now=_dt(1, 10),
    )
    assert results[0][1] is None
    stored = queue.get(p.id)
    assert stored.status == "scheduled"  # will retry
    assert "music-DMCA" in stored.last_error and stored.attempts == 1


def test_run_due_retry_limit_marks_failed(queue):
    p = queue.add("youtube", "c", "a.mp4", "t", RULES, now=_dt(1, 9))

    def boom(post) -> str:
        raise RuntimeError("api down")

    for _ in range(3):
        run_due(queue, {"youtube": boom}, screen=lambda path: True, now=_dt(1, 10))
    stored = queue.get(p.id)
    assert stored.status == "failed" and stored.attempts == 3


def test_run_due_one_failure_does_not_block_others(queue):
    queue.add("youtube", "c1", "a.mp4", "bad", RULES, now=_dt(1, 9))
    queue.add("youtube", "c2", "b.mp4", "good", RULES, now=_dt(1, 9))

    def publisher(post) -> str:
        if post.title == "bad":
            raise RuntimeError("boom")
        return "VID-OK"

    results = run_due(queue, {"youtube": publisher}, screen=lambda p: True, now=_dt(1, 10))
    outcomes = {post.title: ext for post, ext in results}
    assert outcomes == {"bad": None, "good": "VID-OK"}


def test_post_dataclass_shape(queue):
    p = queue.add("youtube", "c", "a.mp4", "t", RULES, now=_dt(1, 9))
    assert isinstance(p, Post) and p.status == "scheduled" and p.attempts == 0
