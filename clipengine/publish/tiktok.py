"""TikTok publishing via the Content Posting API (direct post flow).

Requires a TikTok developer app with the video.publish scope. IMPORTANT: until
the app passes TikTok's audit, direct posts are restricted to
privacy_level=SELF_ONLY (visible only to the posting account) - submit the audit
early, it is the longest external lead time in the project. Creator Rewards pays
only on videos over 1 minute; the CLI warns on shorter uploads.

Flow: init (metadata + file size) -> chunked PUT to the returned upload_url with
Content-Range headers -> poll publish status.
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass

import httpx

from .tokens import TokenSet, TokenStore, valid_access_token

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
QUERY_URL = "https://open.tiktokapis.com/v2/video/query/"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
SCOPE = "video.publish,video.list"  # video.list covers the stats pulls in analytics

# chunk rules per API docs: 5-64 MB per chunk, final chunk may be smaller;
# files up to 64 MB may be sent as a single chunk
_CHUNK = 10 * 1024 * 1024
_SINGLE_CHUNK_MAX = 64 * 1024 * 1024
_POLL_INTERVAL_S = 3.0
_POLL_ATTEMPTS = 40


@dataclass
class PostRequest:
    video_path: str
    caption: str
    privacy_level: str = "SELF_ONLY"  # unaudited apps may only use SELF_ONLY
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False


def build_auth_url(client_key: str, redirect_uri: str, state: str = "clipengine") -> str:
    import urllib.parse

    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": SCOPE,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


class TikTokClient:
    def __init__(
        self,
        client_key: str,
        client_secret: str,
        token_file: str,
        http: httpx.Client | None = None,
        poll_interval_s: float = _POLL_INTERVAL_S,
    ):
        if not client_key or not client_secret:
            raise ValueError(
                "TikTok app credentials missing - set CLIPENGINE_TT_CLIENT_KEY / _SECRET"
            )
        self.client_key = client_key
        self.client_secret = client_secret
        self.store = TokenStore(token_file)
        self.http = http or httpx.Client(timeout=120)
        self.poll_interval_s = poll_interval_s

    # -- auth -------------------------------------------------------------

    def exchange_code(self, code: str, redirect_uri: str) -> TokenSet:
        resp = self.http.post(
            TOKEN_URL,
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        resp.raise_for_status()
        d = resp.json()
        if "access_token" not in d:
            raise RuntimeError(f"TikTok token exchange failed: {d}")
        tokens = TokenSet(
            access_token=d["access_token"],
            refresh_token=d["refresh_token"],
            expires_at=time.time() + float(d.get("expires_in", 86400)),
        )
        self.store.save(tokens)
        return tokens

    def _refresh(self, refresh_token: str) -> TokenSet:
        resp = self.http.post(
            TOKEN_URL,
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        d = resp.json()
        return TokenSet(
            access_token=d["access_token"],
            refresh_token=d.get("refresh_token", refresh_token),  # tiktok rotates: keep new
            expires_at=time.time() + float(d.get("expires_in", 86400)),
        )

    # -- posting ----------------------------------------------------------

    def _chunks(self, size: int) -> tuple[int, int]:
        """(chunk_size, total_chunk_count) per the API's chunking rules."""
        if size <= _SINGLE_CHUNK_MAX:
            return size, 1
        return _CHUNK, math.ceil(size / _CHUNK)

    def post(self, req: PostRequest) -> str:
        """Direct-post a video. Returns the publish_id once TikTok reports success."""
        token = valid_access_token(self.store, self._refresh)
        size = os.path.getsize(req.video_path)
        chunk_size, chunk_count = self._chunks(size)

        init = self.http.post(
            INIT_URL,
            json={
                "post_info": {
                    "title": req.caption,
                    "privacy_level": req.privacy_level,
                    "disable_comment": req.disable_comment,
                    "disable_duet": req.disable_duet,
                    "disable_stitch": req.disable_stitch,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": chunk_count,
                },
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        init.raise_for_status()
        data = init.json().get("data") or {}
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")
        if not publish_id or not upload_url:
            raise RuntimeError(f"TikTok init failed: {init.json()}")

        with open(req.video_path, "rb") as f:
            for i in range(chunk_count):
                chunk = f.read(chunk_size)
                start = i * chunk_size
                end = start + len(chunk) - 1
                put = self.http.put(
                    upload_url,
                    content=chunk,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{size}",
                    },
                )
                put.raise_for_status()

        return self._await_publish(publish_id, token)

    def _await_publish(self, publish_id: str, token: str) -> str:
        for _ in range(_POLL_ATTEMPTS):
            resp = self.http.post(
                STATUS_URL,
                json={"publish_id": publish_id},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            status = data.get("status", "")
            if status == "PUBLISH_COMPLETE":
                # the public video id arrives in this (misspelled by the API)
                # field; analytics needs it - fall back to publish_id otherwise
                public_ids = data.get("publicaly_available_post_id") or []
                return str(public_ids[0]) if public_ids else publish_id
            if status in ("FAILED", "PUBLISH_FAILED"):
                raise RuntimeError(f"TikTok publish failed: {resp.json()}")
            time.sleep(self.poll_interval_s)
        raise TimeoutError(f"TikTok publish {publish_id} still processing - check later")

    # -- stats ------------------------------------------------------------

    def video_stats(self, video_ids: list[str]) -> dict[str, dict]:
        """Fetch per-video statistics -> {video_id: {views, likes, comments, shares}}.

        Uses /v2/video/query/ (video.list scope) with id filters, 20 ids/call.
        """
        token = valid_access_token(self.store, self._refresh)
        out: dict[str, dict] = {}
        for i in range(0, len(video_ids), 20):
            chunk = video_ids[i : i + 20]
            resp = self.http.post(
                QUERY_URL,
                params={"fields": "id,view_count,like_count,comment_count,share_count"},
                json={"filters": {"video_ids": chunk}},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            for v in (resp.json().get("data") or {}).get("videos", []):
                out[str(v["id"])] = {
                    "views": int(v.get("view_count", 0)),
                    "likes": int(v.get("like_count", 0)),
                    "comments": int(v.get("comment_count", 0)),
                    "shares": int(v.get("share_count", 0)),
                }
        return out
