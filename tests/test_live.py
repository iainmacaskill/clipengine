import json

import pytest

from clipengine.config import Config
from clipengine.live.detector import SpikeDetector
from clipengine.live.irc import chat_messages, parse_privmsg
from clipengine.live.monitor import run_live
from clipengine.roster import PermissionError_, Roster


def _detector(**kw):
    d = dict(baseline_s=300, window_s=10, z_threshold=3.0, min_rate=1.0,
             cooldown_s=120, min_baseline_s=60)
    d.update(kw)
    return SpikeDetector(**d)


def _steady(det, start, end, rate):
    """Feed messages at a steady rate; returns any spikes (expected none)."""
    spikes = []
    t = start
    while t < end:
        s = det.add(t)
        if s:
            spikes.append(s)
        t += 1.0 / rate
    return spikes


# -- detector --------------------------------------------------------------


def test_steady_chat_never_triggers():
    det = _detector()
    assert _steady(det, 0, 600, rate=2.0) == []


def test_burst_triggers_after_warmup():
    det = _detector()
    assert _steady(det, 0, 200, rate=1.0) == []
    # burst: 20 msgs/sec for 10 seconds
    spikes = _steady(det, 200, 210, rate=20.0)
    assert len(spikes) == 1
    s = spikes[0]
    # triggers early in the burst (good: lower capture latency), so the window
    # rate is above baseline but not yet at the burst's full 20/s
    assert s.z >= 3.0 and s.rate > s.baseline
    assert 200 <= s.at <= 205  # fired within the first seconds of the burst


def test_burst_during_warmup_ignored():
    det = _detector(min_baseline_s=60)
    spikes = _steady(det, 0, 30, rate=30.0)  # huge burst, but still warming up
    assert spikes == []


def test_cooldown_suppresses_repeat_triggers():
    det = _detector(cooldown_s=120)
    _steady(det, 0, 200, rate=1.0)
    first = _steady(det, 200, 210, rate=20.0)
    assert len(first) == 1
    # second burst 30s later - inside cooldown
    _steady(det, 210, 240, rate=1.0)
    second = _steady(det, 240, 250, rate=20.0)
    assert second == []
    # third burst well after cooldown
    _steady(det, 250, 420, rate=1.0)
    third = _steady(det, 420, 430, rate=20.0)
    assert len(third) == 1


def test_quiet_chat_needs_absolute_rate():
    det = _detector(min_rate=1.0)
    # nearly-dead chat: 1 msg / 20s baseline, then 0.5 msg/s "burst"
    _steady(det, 0, 400, rate=0.05)
    spikes = _steady(det, 400, 410, rate=0.5)
    assert spikes == []  # relative spike but below the absolute floor


# -- IRC -------------------------------------------------------------------


def test_parse_privmsg():
    line = ":nick!nick@nick.tmi.twitch.tv PRIVMSG #somechannel :KEKW no way\r\n"
    assert parse_privmsg(line) == ("nick", "KEKW no way")
    assert parse_privmsg(":tmi.twitch.tv 001 justinfan1 :Welcome") is None


class _FakeSock:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.sent = []

    def sendall(self, data):
        self.sent.append(data.decode())

    def recv(self, n):
        return self._chunks.pop(0) if self._chunks else b""

    def close(self):
        pass


def test_chat_messages_login_ping_and_yield():
    sock = _FakeSock([
        b":tmi.twitch.tv 001 justinfan826774 :Welcome\r\n",
        b"PING :tmi.twitch.tv\r\n",
        b":alice!alice@x PRIVMSG #chan :hello\r\n:bob!bob@x PRIVMSG #chan :KEKW\r\n",
    ])
    clock_t = [100.0]
    msgs = list(chat_messages("Chan", sock=sock, clock=lambda: clock_t[0]))
    assert [(u, m) for _, u, m in msgs] == [("alice", "hello"), ("bob", "KEKW")]
    assert "NICK justinfan826774\r\n" in sock.sent
    assert "JOIN #chan\r\n" in sock.sent  # channel lowercased
    assert "PONG :tmi.twitch.tv\r\n" in sock.sent


# -- monitor ---------------------------------------------------------------


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.work_dir = str(tmp_path / "work")
    c.roster_db = str(tmp_path / "roster.db")
    c.live.min_baseline_s = 60
    c.live.cooldown_s = 120
    with Roster(c.roster_db) as r:
        r.add("nl", source="published_policy", evidence="https://x/p")
    return c


def _chat_source(bursts):
    """Steady 1 msg/s chat with 20 msg/s bursts at the given (start, end) spans."""
    msgs = []
    t = 0.0
    while t < 600:
        in_burst = any(a <= t < b for a, b in bursts)
        step = 0.05 if in_burst else 1.0
        msgs.append((t, "u", "KEKW"))
        t += step
    return iter(msgs)


def test_run_live_requires_roster_permission(cfg, tmp_path):
    with pytest.raises(PermissionError_):
        run_live("unlisted", cfg, iter([]), str(tmp_path / "out"))


def test_run_live_dry_run_records_spikes(cfg, tmp_path):
    out = str(tmp_path / "out")
    events = run_live("nl", cfg, _chat_source([(300, 310)]), out)
    assert len(events) == 1
    assert events[0].clip_id is None and events[0].z >= 3.0
    lines = open(f"{out}/live_events.jsonl").read().strip().splitlines()
    assert json.loads(lines[0])["clip_id"] is None


def test_run_live_captures_on_spike(cfg, tmp_path):
    captured = []

    def capture(spike):
        captured.append(spike.at)
        return "ClipID123", "/clips/live_ClipID123.mp4"

    events = run_live(
        "nl", cfg, _chat_source([(300, 310), (500, 510)]), str(tmp_path / "out"),
        capture=capture,
    )
    assert len(events) == 2 and len(captured) == 2
    assert all(e.clip_path == "/clips/live_ClipID123.mp4" for e in events)


def test_run_live_capture_failure_keeps_monitoring(cfg, tmp_path):
    def capture(spike):
        raise RuntimeError("twitch api down")

    events = run_live(
        "nl", cfg, _chat_source([(300, 310), (500, 510)]), str(tmp_path / "out"),
        capture=capture,
    )
    assert len(events) == 2  # second spike still detected after first failed
    assert all("twitch api down" in e.error for e in events)


def test_run_live_max_events_stops(cfg, tmp_path):
    events = run_live(
        "nl", cfg, _chat_source([(300, 310), (500, 510)]), str(tmp_path / "out"),
        max_events=1,
    )
    assert len(events) == 1


# -- clip API --------------------------------------------------------------


def test_create_clip_requires_user_token():
    from clipengine.config import TwitchConfig
    from clipengine.ingest.twitch import TwitchClient

    client = TwitchClient(TwitchConfig(client_id="x", client_secret="y", user_token=""))
    with pytest.raises(ValueError, match="clips:edit"):
        client._user_headers()


def test_create_and_wait_clip(monkeypatch):
    import httpx

    from clipengine.config import TwitchConfig
    from clipengine.ingest.twitch import TwitchClient

    client = TwitchClient(
        TwitchConfig(client_id="x", client_secret="y", user_token="usertok")
    )
    client._token = "apptok"
    monkeypatch.setattr(client, "user_id", lambda login: "42")

    def fake_post(url, params=None, headers=None):
        assert params == {"broadcaster_id": "42"}
        assert headers["Authorization"] == "Bearer usertok"
        return httpx.Response(202, json={"data": [{"id": "CLIP1", "edit_url": "..."}]},
                              request=httpx.Request("POST", url))

    pending = {"polls": 0}

    def fake_get(url, params=None, headers=None):
        pending["polls"] += 1
        data = [] if pending["polls"] < 3 else [{"id": "CLIP1", "url": "https://clip"}]
        return httpx.Response(200, json={"data": data}, request=httpx.Request("GET", url))

    monkeypatch.setattr("clipengine.ingest.twitch.httpx.post", fake_post)
    monkeypatch.setattr("clipengine.ingest.twitch.httpx.get", fake_get)

    clip_id = client.create_clip("nl")
    assert clip_id == "CLIP1"
    clip = client.wait_clip(clip_id, timeout_s=30, poll_s=1, sleep=lambda s: None)
    assert clip["url"] == "https://clip" and pending["polls"] == 3
