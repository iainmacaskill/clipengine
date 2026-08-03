import json

import pytest

from clipengine.campaigns.models import Campaign
from clipengine.campaigns.store import CampaignStore
from clipengine.config import Config
from clipengine.web import api
from clipengine.web.jobs import JobRegistry
from clipengine.web.store import SourceStore


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.campaigns.campaigns_db = str(tmp_path / "campaigns.db")
    c.work_dir = str(tmp_path / "work")
    return c


@pytest.fixture
def frida(cfg):
    with CampaignStore(cfg.campaigns.campaigns_db) as store:
        store.upsert([Campaign(
            id="disc:frida", source="manual", title="Frida — Chelsea Hirschhorn",
            brand="Frida", status="open", reward_model="cpm", reward_amount=2.0,
            budget_total=5000.0, budget_remaining=4820.0, platforms=["tiktok"],
            rules_text=(
                "Tag @fridamom. Identify Chelsea Hirschhorn as CEO and Founder. "
                "Minimum 10 seconds. TikTok only. #ad. "
                "Approved source: https://youtube.com/watch?v=goop-chelsea"
            ),
        )], at="t1")
    return "disc:frida"


@pytest.fixture
def sources(tmp_path):
    s = SourceStore(str(tmp_path / "sources.db"))
    yield s
    s.close()


# ---- campaigns -------------------------------------------------------------


def test_list_campaigns_scored(cfg, frida):
    code, body = api.list_campaigns(cfg)
    assert code == 200
    assert body["campaigns"][0]["id"] == "disc:frida"
    assert body["campaigns"][0]["reward_amount"] == 2.0
    assert body["campaigns"][0]["score"] > 0


def test_get_campaign_translates_rules(cfg, frida):
    code, body = api.get_campaign(cfg, "disc:frida")
    assert code == 200
    ck = body["checklist"]
    assert "fridamom" in ck["mentions"]
    assert "ad" in ck["hashtags"]
    assert ck["min_duration_s"] == 10
    assert "tiktok" in ck["platforms"]
    assert body["caption_suffix"]  # required tokens for the UI to lock in


def test_get_campaign_404(cfg):
    code, _body = api.get_campaign(cfg, "nope")
    assert code == 404


def test_add_campaign(cfg):
    code, body = api.add_campaign(cfg, {
        "title": "Test Co", "cpm": "1.5", "budget": "3000",
        "platforms": "tiktok,instagram", "rules_text": "Tag @test #go",
    })
    assert code == 201
    assert body["id"] == "manual:test-co"
    assert body["reward_amount"] == 1.5
    _code2, body2 = api.list_campaigns(cfg)
    assert any(c["id"] == "manual:test-co" for c in body2["campaigns"])


def test_add_campaign_requires_title(cfg):
    code, _body = api.add_campaign(cfg, {"cpm": "1"})
    assert code == 400


# ---- sources + approved-link enforcement -----------------------------------


def test_add_source_rejects_unapproved_link(cfg, frida, sources):
    code, body = api.add_source(cfg, sources, {
        "campaign_id": "disc:frida", "url": "https://youtube.com/watch?v=RANDOM",
    })
    assert code == 400
    assert "approved" in body


def test_add_source_accepts_approved_link(cfg, frida, sources):
    code, body = api.add_source(cfg, sources, {
        "campaign_id": "disc:frida", "url": "https://youtube.com/watch?v=goop-chelsea",
    })
    assert code == 201
    assert body["status"] == "pending"


def test_add_source_accepts_local_path(cfg, frida, sources):
    code, body = api.add_source(cfg, sources, {
        "campaign_id": "disc:frida", "path": "/videos/goop.mp4",
    })
    assert code == 201
    assert body["status"] == "ready"  # a file on disk needs no download


def test_add_source_no_link_or_path(cfg, frida, sources):
    code, _body = api.add_source(cfg, sources, {"campaign_id": "disc:frida"})
    assert code == 400


def test_link_allowed_when_no_approved_list(cfg, sources):
    # a campaign with no source links doesn't constrain sources
    with CampaignStore(cfg.campaigns.campaigns_db) as store:
        store.upsert([Campaign(id="c2", source="manual", title="Open", status="open",
                               rules_text="Tag @x")], at="t1")
    code, _ = api.add_source(cfg, sources, {"campaign_id": "c2",
                                            "url": "https://example.com/anything"})
    assert code == 201


# ---- jobs ------------------------------------------------------------------


def test_prepare_job_transcribes_then_ready(cfg, frida, sources, tmp_path, monkeypatch):
    vid = tmp_path / "goop.mp4"
    vid.write_text("video")
    src = sources.add("disc:frida", path=str(vid))

    from clipengine.edit import ffmpeg as edit
    from clipengine.models import SourceVideo, Transcript
    monkeypatch.setattr(edit, "probe", lambda p: SourceVideo(p, 1920, 1080, 51.0))
    from clipengine import pipeline
    monkeypatch.setattr(pipeline, "source_transcript",
                        lambda p, c: Transcript(segments=[]))

    reg = JobRegistry()
    job = reg.create("prepare")
    reg.run(job, api.job_prepare_source(cfg, sources.path, src.id), background=False)
    assert job.status == "done", job.error
    assert sources.get(src.id).status == "ready"
    assert sources.get(src.id).duration_s == 51.0


def test_detect_job_returns_moments_with_excerpts(cfg, frida, sources, tmp_path, monkeypatch):
    vid = tmp_path / "goop.mp4"
    vid.write_text("video")
    src = sources.add("disc:frida", path=str(vid))

    from clipengine import pipeline
    from clipengine.models import ClipCandidate, Transcript, TranscriptSegment
    monkeypatch.setattr(pipeline, "detect_candidates",
                        lambda v, ch, c: [ClipCandidate(start=10.0, end=45.0, score=0.35)])
    monkeypatch.setattr(pipeline, "source_transcript", lambda p, c: Transcript(
        segments=[TranscriptSegment(20.0, 30.0, "the curse of competency", [])]))

    reg = JobRegistry()
    job = reg.create("detect")
    reg.run(job, api.job_detect(cfg, sources.path, src.id), background=False)
    assert job.status == "done", job.error
    m = job.result["moments"][0]
    assert m["start"] == 10.0 and m["score"] == 0.35
    assert "curse of competency" in m["excerpt"]


def test_detect_job_errors_without_prepared_source(cfg, frida, sources):
    src = sources.add("disc:frida", path="/gone/missing.mp4")
    reg = JobRegistry()
    job = reg.create("detect")
    reg.run(job, api.job_detect(cfg, sources.path, src.id), background=False)
    assert job.status == "error"
    assert "prepare" in job.message.lower()


def test_render_job_builds_caption_and_gates(cfg, frida, sources, tmp_path, monkeypatch):
    vid = tmp_path / "goop.mp4"
    vid.write_text("video")
    src = sources.add("disc:frida", url="https://youtube.com/watch?v=goop-chelsea")
    sources.update(src.id, path=str(vid), status="ready")

    from clipengine import pipeline
    from clipengine.models import Transcript, TranscriptSegment
    monkeypatch.setattr(pipeline, "source_transcript", lambda p, c: Transcript(
        segments=[TranscriptSegment(0.0, 40.0, "hello", [])]))
    monkeypatch.setattr(pipeline, "snap_to_speech", lambda t, s, e: (s, e))
    rendered = {}
    monkeypatch.setattr(pipeline, "repurpose_asset",
                        lambda *a, **k: rendered.setdefault("out", a[1]) or a[1])

    reg = JobRegistry()
    job = reg.create("render")
    clips = [{"source_id": src.id, "start": 10.0, "end": 45.0,
              "hook": "the *curse* of competency", "style": "clean",
              "caption": "sharing what most CEOs never would",
              "out_name": "frida11", "platform": "tiktok"}]
    reg.run(job, api.job_render(cfg, sources.path, clips), background=False)
    assert job.status == "done", job.error
    clip = job.result["clips"][0]
    # required tokens appended to the caption
    assert "@fridamom" in clip["caption"] and "#ad" in clip["caption"]
    # gate ran and passed (approved source, tiktok, >=10s, tokens present)
    assert clip["gate"]["passed"], clip["gate"]
    assert "out" in rendered


def test_render_job_isolates_one_clip_failure(cfg, frida, sources, tmp_path, monkeypatch):
    src = sources.add("disc:frida", path="/gone.mp4")  # will fail in _render_one
    reg = JobRegistry()
    job = reg.create("render")
    reg.run(job, api.job_render(cfg, sources.path,
                                [{"source_id": src.id, "start": 0, "end": 10}]),
            background=False)
    assert job.status == "done"  # batch survives
    assert "error" in job.result["clips"][0]


# ---- submissions -----------------------------------------------------------


def test_add_and_list_submission(cfg, frida):
    code, _body = api.add_submission(cfg, {
        "campaign_id": "disc:frida", "post_url": "https://tiktok.com/@me/video/1",
        "platform": "tiktok",
    })
    assert code == 201
    _code2, body2 = api.list_submissions(cfg, "disc:frida")
    assert body2["submissions"][0]["post_url"].endswith("/1")


def test_add_submission_requires_url(cfg, frida):
    code, _ = api.add_submission(cfg, {"campaign_id": "disc:frida"})
    assert code == 400


# ---- routing / server smoke ------------------------------------------------


def test_dispatch_routes(cfg, frida, monkeypatch, tmp_path):
    from clipengine.web import server
    state = server.AppState(cfg)
    code, body = server.dispatch(state, "GET", "/api/campaigns", None)
    assert code == 200 and body["campaigns"]
    code, body = server.dispatch(state, "GET", "/api/campaigns/disc:frida", None)
    assert code == 200 and body["checklist"]["mentions"] == ["fridamom"]
    code, body = server.dispatch(state, "GET", "/api/nope", None)
    assert code == 404


def test_dispatch_unknown_route(cfg):
    from clipengine.web import server
    state = server.AppState(cfg)
    code, _ = server.dispatch(state, "DELETE", "/api/campaigns", None)
    assert code == 404


def test_server_end_to_end(cfg, frida):
    """A real socket: start the server, hit two endpoints, stop it."""
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    from clipengine.web import server as srv
    state = srv.AppState(cfg)
    handler = type("H", (srv._Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/campaigns") as r:
            data = json.loads(r.read())
        assert data["campaigns"][0]["id"] == "disc:frida"
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/campaigns",
            data=json.dumps({"title": "Via HTTP", "cpm": "1", "budget": "100"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req) as r:
            assert r.status == 201
        # static index served at /
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as r:
            assert b"CLIP STUDIO" in r.read()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_server_decodes_percent_encoded_ids(cfg, frida):
    """Browsers percent-encode the ':' in ids like disc:frida; the server must
    decode the path before lookup or every campaign 404s."""
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    from clipengine.web import server as srv
    state = srv.AppState(cfg)
    handler = type("H", (srv._Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{port}/api/campaigns/disc%3Afrida"
        with urllib.request.urlopen(url) as r:
            data = json.loads(r.read())
        assert data["id"] == "disc:frida"
        assert data["checklist"]["mentions"] == ["fridamom"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_static_path_traversal_blocked(cfg):
    """The static server must not escape its directory."""
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    from clipengine.web import server as srv
    state = srv.AppState(cfg)
    handler = type("H", (srv._Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/../../etc/passwd")
            got = 200
        except urllib.error.HTTPError as e:
            got = e.code
        assert got == 404
    finally:
        httpd.shutdown()
        httpd.server_close()
