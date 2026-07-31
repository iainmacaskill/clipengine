import json

import pytest

from clipengine.package import hooks
from clipengine.package.hooks import Suggestion, generate


class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, payload, stop_reason="end_turn"):
        self.stop_reason = stop_reason
        self.content = [_FakeBlock(json.dumps(payload))] if payload is not None else []


class _FakeClient:
    """Mimics anthropic.Anthropic().beta.messages.create for injection."""

    def __init__(self, response):
        self._response = response
        self.calls = []

        outer = self

        class _Messages:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return outer._response

        class _Beta:
            messages = _Messages()

        self.beta = _Beta()


def _payload(**kw):
    d = {"hook": "he did NOT expect this", "title": "The greatest ward of all time",
         "hashtags": ["gaming", "leagueoflegends", "fail"]}
    d.update(kw)
    return d


def test_generate_returns_suggestion_and_sends_transcript():
    client = _FakeClient(_FakeResponse(_payload()))
    s = generate("I flashed into five people chat", "northernlion", client=client)
    assert s == Suggestion(
        hook="he did NOT expect this",
        title="The greatest ward of all time",
        hashtags=["gaming", "leagueoflegends", "fail"],
    )
    call = client.calls[0]
    assert call["model"] == "claude-opus-5"
    assert "I flashed into five people" in call["messages"][0]["content"]
    assert "northernlion" in call["messages"][0]["content"]
    # structured output schema requested; server-side fallbacks enabled
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["fallbacks"] == "default"


def test_refusal_returns_none():
    client = _FakeClient(_FakeResponse(None, stop_reason="refusal"))
    assert generate("some transcript", "nl", client=client) is None


def test_hashtags_normalised_and_deduped():
    client = _FakeClient(
        _FakeResponse(_payload(hashtags=["#Gaming", "gaming", "  #FYP ", "twitch clips"]))
    )
    s = generate("t", "nl", client=client)
    assert s.hashtags == ["gaming", "fyp", "twitchclips"]


def test_hook_quotes_stripped():
    client = _FakeClient(_FakeResponse(_payload(hook='"NO WAY he did that"')))
    assert generate("t", "nl", client=client).hook == "NO WAY he did that"


def test_empty_transcript_skips_api_call():
    client = _FakeClient(_FakeResponse(_payload()))
    assert generate("   ", "nl", client=client) is None
    assert client.calls == []


def test_malformed_json_returns_none():
    client = _FakeClient(_FakeResponse(None))
    client._response.content = [_FakeBlock("not json {")]
    assert generate("t", "nl", client=client) is None


def test_available_tracks_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not hooks.available()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert hooks.available()


# -- pipeline integration --------------------------------------------------


def test_process_attaches_suggestions_and_burns_hook(tmp_path, monkeypatch):
    from clipengine import pipeline
    from clipengine.config import Config
    from clipengine.detect.transcribe import save
    from clipengine.models import ClipCandidate, FacecamRegion, Transcript, TranscriptSegment
    from clipengine.roster import Roster

    cfg = Config()
    cfg.work_dir = str(tmp_path / "work")
    cfg.roster_db = str(tmp_path / "roster.db")
    with Roster(cfg.roster_db) as r:
        r.add("nl", source="published_policy", evidence="https://x/p")

    monkeypatch.setattr(
        pipeline, "detect_candidates",
        lambda v, c, cf: [ClipCandidate(start=10.0, end=85.0, score=2.0)],
    )

    def fake_render(video, cand, facecam, out_path, cf, with_captions=True,
                    credit_text=None, transcript_out=None):
        open(out_path, "w").write("clip")
        if transcript_out:
            save(Transcript(segments=[TranscriptSegment(0, 5, "wait what is that")]),
                 transcript_out)
        return out_path

    monkeypatch.setattr(pipeline, "render_candidate", fake_render)
    monkeypatch.setattr(pipeline.audio, "extract_wav", lambda v, w: w)
    monkeypatch.setattr("clipengine.package.music.check", lambda wav, threshold=0.3: [])
    burned = []
    monkeypatch.setattr(
        pipeline.edit, "burn_hook",
        lambda src, dst, text, ecfg: (burned.append(text), open(dst, "w").write("hooked"))[1] or dst,
    )

    def fake_suggest(text, streamer):
        assert "wait what is that" in text and streamer == "nl"
        return Suggestion(hook="WAIT FOR IT", title="unbelievable moment", hashtags=["gaming"])

    manifest = pipeline.process_vod(
        "v.mp4", None, "nl", str(tmp_path / "out"), cfg,
        facecam=FacecamRegion(0, 0, 10, 10), suggest=fake_suggest,
    )
    m = manifest[0]
    assert m["hook"] == "WAIT FOR IT"
    assert m["suggested_title"] == "unbelievable moment"
    assert m["hashtags"] == ["gaming"]
    assert burned == ["WAIT FOR IT"]
    assert open(m["path"]).read() == "hooked"  # hooked render replaced the original


def test_process_without_suggest_still_renders(tmp_path, monkeypatch):
    from clipengine import pipeline
    from clipengine.config import Config
    from clipengine.models import ClipCandidate, FacecamRegion
    from clipengine.roster import Roster

    cfg = Config()
    cfg.work_dir = str(tmp_path / "work")
    cfg.roster_db = str(tmp_path / "roster.db")
    with Roster(cfg.roster_db) as r:
        r.add("nl", source="published_policy", evidence="https://x/p")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        pipeline, "detect_candidates",
        lambda v, c, cf: [ClipCandidate(start=1.0, end=20.0, score=1.0)],
    )
    monkeypatch.setattr(
        pipeline, "render_candidate",
        lambda *a, **k: open(a[3], "w").write("clip") and a[3] or a[3],
    )
    monkeypatch.setattr(pipeline.audio, "extract_wav", lambda v, w: w)
    monkeypatch.setattr("clipengine.package.music.check", lambda wav, threshold=0.3: [])
    manifest = pipeline.process_vod(
        "v.mp4", None, "nl", str(tmp_path / "out"), cfg,
        facecam=FacecamRegion(0, 0, 10, 10),
    )
    assert manifest[0]["status"] == "rendered"
    assert "hook" not in manifest[0]
