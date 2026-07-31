import httpx

from clipengine.config import DetectConfig
from clipengine.detect.tune import evaluate, to_config_toml, tune, weight_grid
from clipengine.models import ClipCandidate, SignalSeries


def _cand(start, end):
    return ClipCandidate(start=start, end=end, score=1.0)


# -- evaluate -------------------------------------------------------------


def test_evaluate_counts_covered_moments():
    candidates = [_cand(100, 175), _cand(300, 375)]
    truth = [{"offset": 120}, {"offset": 320}, {"offset": 500}]
    ev = evaluate(candidates, truth)
    assert ev.hits == 2 and ev.n_truth == 3
    assert abs(ev.recall - 2 / 3) < 1e-9
    assert ev.mean_hit_rank == 0.5  # ranks 0 and 1


def test_evaluate_top_n_limits_candidates():
    candidates = [_cand(0, 50), _cand(100, 150)]
    truth = [{"offset": 120}]
    assert evaluate(candidates, truth, top_n=1).hits == 0
    assert evaluate(candidates, truth, top_n=2).hits == 1


def test_evaluate_top_truth_limits_moments():
    candidates = [_cand(0, 50)]
    truth = [{"offset": 10}, {"offset": 999}]
    ev = evaluate(candidates, truth, top_truth=1)
    assert ev.recall == 1.0 and ev.n_truth == 1


def test_evaluate_empty_truth():
    assert evaluate([_cand(0, 10)], []).recall == 0.0


# -- grid / tune ----------------------------------------------------------


def test_weight_grid_excludes_all_zero():
    grid = weight_grid(("a", "b"), (0.0, 1.0))
    assert {"a": 0.0, "b": 0.0} not in grid
    assert len(grid) == 3


def _spiky(length, spikes, value=8.0):
    scores = [0.0] * length
    for s in spikes:
        for i in range(s, min(s + 8, length)):
            scores[i] = value
    return scores


def test_tune_prefers_the_informative_signal():
    """Truth moments align with chat spikes; audio spikes elsewhere are decoys."""
    duration = 599.0
    chat = SignalSeries("chat_velocity", _spiky(600, [100, 300, 500]))
    audio = SignalSeries("audio_energy", _spiky(600, [50, 200, 400]))
    truth = [{"offset": 104}, {"offset": 304}, {"offset": 504}]
    cfg = DetectConfig(target_duration=40.0, min_gap=10.0, top_n=3, pre_roll=5.0)

    results = tune([chat, audio], duration, truth, cfg, top_truth=3)
    best_weights, best_eval = results[0]
    assert best_eval.recall == 1.0
    assert best_weights["chat_velocity"] > 0
    # any config ignoring chat entirely must do strictly worse
    chatless = [ev for w, ev in results if w.get("chat_velocity") == 0]
    assert all(ev.recall < 1.0 for ev in chatless)


def test_tune_results_sorted_by_recall():
    duration = 299.0
    chat = SignalSeries("chat_velocity", _spiky(300, [100]))
    truth = [{"offset": 104}]
    cfg = DetectConfig(target_duration=30.0, min_gap=10.0, top_n=2, pre_roll=5.0)
    results = tune([chat], duration, truth, cfg, top_truth=1)
    recalls = [ev.recall for _, ev in results]
    assert recalls == sorted(recalls, reverse=True)


def test_to_config_toml():
    snippet = to_config_toml({"chat_velocity": 1.0, "audio_energy": 0.25})
    assert snippet.startswith("[detect]")
    assert "weight_chat_velocity = 1" in snippet
    assert "weight_audio_energy = 0.25" in snippet


# -- ground-truth fetcher -------------------------------------------------


def test_vod_clips_filters_and_sorts(monkeypatch):
    from clipengine.config import TwitchConfig
    from clipengine.ingest.twitch import TwitchClient

    pages = [
        {
            "data": [
                {"video_id": "V1", "vod_offset": 120, "view_count": 50,
                 "duration": 28.0, "title": "big play"},
                {"video_id": "V1", "vod_offset": None, "view_count": 999,
                 "duration": 20.0, "title": "no offset - dropped"},
                {"video_id": "OTHER", "vod_offset": 10, "view_count": 999,
                 "duration": 20.0, "title": "other vod - dropped"},
            ],
            "pagination": {"cursor": "C1"},
        },
        {
            "data": [
                {"video_id": "V1", "vod_offset": 700, "view_count": 300,
                 "duration": 30.0, "title": "even bigger"},
            ],
            "pagination": {},
        },
    ]
    state = {"i": 0}

    def fake_get(url, params=None, headers=None):
        req = httpx.Request("GET", url)
        if url.endswith("/users"):
            return httpx.Response(200, json={"data": [{"id": "42"}]}, request=req)
        page = pages[state["i"]]
        state["i"] += 1
        return httpx.Response(200, json=page, request=req)

    monkeypatch.setattr("clipengine.ingest.twitch.httpx.get", fake_get)
    client = TwitchClient(TwitchConfig(client_id="x", client_secret="y"))
    client._token = "tok"
    clips = client.vod_clips("streamer", "V1")
    assert [c["offset"] for c in clips] == [700.0, 120.0]  # views-descending
    assert clips[0]["views"] == 300
