import json
import time

import httpx
import pytest

from clipengine.publish.tiktok import PostRequest, TikTokClient
from clipengine.publish.tokens import TokenSet, TokenStore, valid_access_token
from clipengine.publish.youtube import UploadRequest, YouTubeClient


def _fresh_tokens():
    return TokenSet("live-token", "refresh-token", time.time() + 3600)


def _stale_tokens():
    return TokenSet("stale-token", "refresh-token", time.time() - 10)


# -- token store ----------------------------------------------------------


def test_token_store_roundtrip(tmp_path):
    store = TokenStore(str(tmp_path / "t.json"))
    assert store.load() is None
    store.save(_fresh_tokens())
    loaded = store.load()
    assert loaded.access_token == "live-token" and not loaded.expired


def test_valid_access_token_refreshes_when_stale(tmp_path):
    store = TokenStore(str(tmp_path / "t.json"))
    store.save(_stale_tokens())
    refreshed = TokenSet("new-token", "rotated-refresh", time.time() + 3600)
    token = valid_access_token(store, lambda rt: refreshed)
    assert token == "new-token"
    assert store.load().refresh_token == "rotated-refresh"  # rotation persisted


def test_valid_access_token_requires_auth_first(tmp_path):
    store = TokenStore(str(tmp_path / "t.json"))
    with pytest.raises(RuntimeError, match="clipengine auth"):
        valid_access_token(store, lambda rt: _fresh_tokens())


# -- youtube --------------------------------------------------------------


def _youtube_client(tmp_path, handler):
    store_path = str(tmp_path / "yt.json")
    TokenStore(store_path).save(_fresh_tokens())
    return YouTubeClient(
        "cid", "csecret", store_path, http=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_youtube_resumable_upload(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"FAKE-MP4-BYTES")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "uploadType=resumable" in str(request.url):
            seen["init"] = json.loads(request.content)
            seen["init_headers"] = dict(request.headers)
            return httpx.Response(
                200, headers={"Location": "https://upload.example/session-1"}
            )
        if request.method == "PUT" and "session-1" in str(request.url):
            seen["bytes"] = request.content
            return httpx.Response(200, json={"id": "VID123"})
        return httpx.Response(404)

    client = _youtube_client(tmp_path, handler)
    video_id = client.upload(
        UploadRequest(str(video), title="Insane clutch #Shorts", tags=["gaming"], privacy="unlisted")
    )
    assert video_id == "VID123"
    assert seen["init"]["snippet"]["title"] == "Insane clutch #Shorts"
    assert seen["init"]["snippet"]["categoryId"] == "20"
    assert seen["init"]["status"]["privacyStatus"] == "unlisted"
    assert seen["init_headers"]["authorization"] == "Bearer live-token"
    assert seen["bytes"] == b"FAKE-MP4-BYTES"


def test_youtube_missing_location_raises(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")

    def handler(request):
        return httpx.Response(200, json={})

    client = _youtube_client(tmp_path, handler)
    with pytest.raises(RuntimeError, match="no session Location"):
        client.upload(UploadRequest(str(video), title="t"))


# -- tiktok ---------------------------------------------------------------


def _tiktok_client(tmp_path, handler):
    store_path = str(tmp_path / "tt.json")
    TokenStore(store_path).save(_fresh_tokens())
    return TikTokClient(
        "key", "secret", store_path,
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_s=0,
    )


def test_tiktok_direct_post_flow(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"A" * 1000)
    seen = {"puts": []}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/video/init/"):
            seen["init"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={"data": {"publish_id": "PUB1", "upload_url": "https://up.example/u1"}},
            )
        if "up.example" in url:
            seen["puts"].append(dict(request.headers))
            return httpx.Response(200)
        if url.endswith("/status/fetch/"):
            return httpx.Response(200, json={"data": {"status": "PUBLISH_COMPLETE"}})
        return httpx.Response(404)

    client = _tiktok_client(tmp_path, handler)
    publish_id = client.post(PostRequest(str(video), caption="clip time"))
    assert publish_id == "PUB1"
    src = seen["init"]["source_info"]
    assert src == {
        "source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000, "total_chunk_count": 1,
    }
    assert seen["init"]["post_info"]["privacy_level"] == "SELF_ONLY"
    assert seen["puts"][0]["content-range"] == "bytes 0-999/1000"


def test_tiktok_chunking_rules(tmp_path):
    client = _tiktok_client(tmp_path, lambda r: httpx.Response(404))
    assert client._chunks(1000) == (1000, 1)
    assert client._chunks(64 * 1024 * 1024) == (64 * 1024 * 1024, 1)
    size = 100 * 1024 * 1024
    chunk, count = client._chunks(size)
    assert chunk == 10 * 1024 * 1024 and count == 10


def test_tiktok_publish_failure_raises(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/video/init/"):
            return httpx.Response(
                200, json={"data": {"publish_id": "PUB1", "upload_url": "https://up.example/u1"}}
            )
        if "up.example" in url:
            return httpx.Response(200)
        return httpx.Response(200, json={"data": {"status": "FAILED"}})

    client = _tiktok_client(tmp_path, handler)
    with pytest.raises(RuntimeError, match="publish failed"):
        client.post(PostRequest(str(video), caption="x"))


# -- CLI music gate --------------------------------------------------------


def test_publish_cli_refuses_music_flagged_clip(tmp_path, monkeypatch, capsys):
    from clipengine import cli
    from clipengine.package.music import MusicSegment

    monkeypatch.setattr(
        "clipengine.detect.audio.extract_wav", lambda v, w: w
    )
    monkeypatch.setattr(
        "clipengine.package.music.check",
        lambda wav, threshold=0.3: [MusicSegment(5.0, 20.0, 0.6)],
    )
    uploaded = {}
    monkeypatch.setattr(
        "clipengine.publish.youtube.YouTubeClient.upload",
        lambda self, req: uploaded.setdefault("id", "X"),
    )
    cfg_file = tmp_path / "cfg.toml"
    cfg_file.write_text(f'work_dir = "{tmp_path}"\n')
    rc = cli.main(
        ["--config", str(cfg_file), "publish", "youtube", "clip.mp4", "--title", "t"]
    )
    assert rc == 3
    assert "publish refused" in capsys.readouterr().err
    assert uploaded == {}
