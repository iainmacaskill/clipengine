"""YouTube Shorts publishing via the Data API v3 resumable upload protocol.

A Short is an ordinary upload that is vertical and <=3 minutes; #Shorts in the
title/description helps surfacing. Uses an OAuth installed-app client: create one
in Google Cloud Console (YouTube Data API v3 enabled), then run
``clipengine auth youtube`` once per channel to mint the token file.

Quota note: videos.insert costs 1600 units of the 10k/day default quota -
about 6 uploads/day per project until a quota increase is granted. Plan
accordingly for multi-channel operation.
"""
from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass, field

import httpx

from .tokens import TokenSet, TokenStore, valid_access_token

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
# upload + readonly: readonly covers the stats pulls in analytics
SCOPE = (
    "https://www.googleapis.com/auth/youtube.upload "
    "https://www.googleapis.com/auth/youtube.readonly"
)
_CATEGORY_GAMING = "20"


@dataclass
class UploadRequest:
    video_path: str
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    privacy: str = "private"  # private | unlisted | public


def build_auth_url(client_id: str, redirect_uri: str) -> str:
    """Consent URL for the one-time per-channel authorisation (run in a browser)."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",  # required to receive a refresh token
        "prompt": "consent",
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


class YouTubeClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_file: str,
        http: httpx.Client | None = None,
    ):
        if not client_id or not client_secret:
            raise ValueError(
                "YouTube OAuth client missing - set CLIPENGINE_YT_CLIENT_ID / _SECRET"
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.store = TokenStore(token_file)
        self.http = http or httpx.Client(timeout=120)

    # -- auth -------------------------------------------------------------

    def exchange_code(self, code: str, redirect_uri: str) -> TokenSet:
        """Complete the one-time consent flow; persists and returns the tokens."""
        import time

        resp = self.http.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        resp.raise_for_status()
        d = resp.json()
        tokens = TokenSet(
            access_token=d["access_token"],
            refresh_token=d["refresh_token"],
            expires_at=time.time() + float(d.get("expires_in", 3600)),
        )
        self.store.save(tokens)
        return tokens

    def _refresh(self, refresh_token: str) -> TokenSet:
        import time

        resp = self.http.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        d = resp.json()
        return TokenSet(
            access_token=d["access_token"],
            refresh_token=d.get("refresh_token", refresh_token),  # google doesn't rotate
            expires_at=time.time() + float(d.get("expires_in", 3600)),
        )

    # -- upload -----------------------------------------------------------

    def upload(self, req: UploadRequest) -> str:
        """Resumable upload: init session -> PUT bytes. Returns the video id."""
        token = valid_access_token(self.store, self._refresh)
        size = os.path.getsize(req.video_path)
        metadata = {
            "snippet": {
                "title": req.title,
                "description": req.description,
                "tags": req.tags,
                "categoryId": _CATEGORY_GAMING,
            },
            "status": {
                "privacyStatus": req.privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        init = self.http.post(
            UPLOAD_URL + "?uploadType=resumable&part=snippet,status",
            json=metadata,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(size),
            },
        )
        init.raise_for_status()
        session_url = init.headers.get("Location")
        if not session_url:
            raise RuntimeError("YouTube resumable init returned no session Location")

        with open(req.video_path, "rb") as f:
            put = self.http.put(
                session_url,
                content=f.read(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "video/mp4",
                    "Content-Length": str(size),
                },
            )
        put.raise_for_status()
        body = put.json()
        if "id" not in body:
            raise RuntimeError(f"YouTube upload response missing id: {body}")
        return body["id"]

    # -- stats ------------------------------------------------------------

    def stats(self, video_ids: list[str]) -> dict[str, dict]:
        """Fetch per-video statistics -> {video_id: {views, likes, comments}}.

        videos.list costs 1 quota unit per call (50 ids/call) - negligible next
        to uploads.
        """
        token = valid_access_token(self.store, self._refresh)
        out: dict[str, dict] = {}
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i : i + 50]
            resp = self.http.get(
                VIDEOS_URL,
                params={"part": "statistics", "id": ",".join(chunk)},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                s = item.get("statistics", {})
                out[item["id"]] = {
                    "views": int(s.get("viewCount", 0)),
                    "likes": int(s.get("likeCount", 0)),
                    "comments": int(s.get("commentCount", 0)),
                    "shares": 0,  # not exposed by the API
                }
        return out
