"""Twitch ingestion: Helix API client for VOD discovery, plus chat-log normalisation.

Status: skeleton. Auth + VOD listing are implemented against the public Helix API;
VOD video download and chat replay download are TODO (both have several viable
routes - see notes on each function). Only ingest streamers on the permission
roster (see product plan section 2).
"""
from __future__ import annotations

import json

import httpx

from ..config import TwitchConfig
from ..models import ChatMessage

_HELIX = "https://api.twitch.tv/helix"
_OAUTH = "https://id.twitch.tv/oauth2/token"


class TwitchClient:
    def __init__(self, cfg: TwitchConfig):
        if not cfg.client_id or not cfg.client_secret:
            raise ValueError(
                "Twitch credentials missing - set CLIPENGINE_TWITCH_CLIENT_ID / _SECRET"
            )
        self.cfg = cfg
        self._token: str | None = None

    def _auth_headers(self) -> dict[str, str]:
        if self._token is None:
            resp = httpx.post(
                _OAUTH,
                data={
                    "client_id": self.cfg.client_id,
                    "client_secret": self.cfg.client_secret,
                    "grant_type": "client_credentials",
                },
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        return {"Client-Id": self.cfg.client_id, "Authorization": f"Bearer {self._token}"}

    def user_id(self, login: str) -> str:
        resp = httpx.get(_HELIX + "/users", params={"login": login}, headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()["data"]
        if not data:
            raise LookupError(f"no Twitch user: {login}")
        return data[0]["id"]

    def recent_vods(self, login: str, limit: int = 5) -> list[dict]:
        """Most recent archive VODs for a streamer (id, title, duration, created_at)."""
        uid = self.user_id(login)
        resp = httpx.get(
            _HELIX + "/videos",
            params={"user_id": uid, "type": "archive", "first": limit},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()["data"]

    def vod_clips(
        self, login: str, vod_id: str, max_pages: int = 10, first: int = 100
    ) -> list[dict]:
        """Viewer-created clips of one VOD, with their VOD offsets, views-descending.

        This is detector ground truth: the moments the audience itself clipped.
        Helix /clips only filters by broadcaster, so we page through recent clips
        and keep the ones from this VOD that carry a vod_offset.
        """
        uid = self.user_id(login)
        clips: list[dict] = []
        cursor: str | None = None
        for _ in range(max_pages):
            params: dict = {"broadcaster_id": uid, "first": first}
            if cursor:
                params["after"] = cursor
            resp = httpx.get(_HELIX + "/clips", params=params, headers=self._auth_headers())
            resp.raise_for_status()
            data = resp.json()
            for c in data.get("data", []):
                if c.get("video_id") == vod_id and c.get("vod_offset") is not None:
                    clips.append(
                        {
                            "offset": float(c["vod_offset"]),
                            "duration": float(c.get("duration", 30.0)),
                            "views": int(c.get("view_count", 0)),
                            "title": c.get("title", ""),
                        }
                    )
            cursor = (data.get("pagination") or {}).get("cursor")
            if not cursor:
                break
        clips.sort(key=lambda c: -c["views"])
        return clips

    def download_vod(self, vod_id: str, dst_path: str) -> str:
        """Download a VOD's video via yt-dlp (see ingest.vod for routes/auth notes)."""
        from .vod import download_vod

        return download_vod(vod_id, dst_path)

    def download_chat(self, vod_id: str, dst_path: str) -> str:
        """Download the VOD chat replay to the pipeline's JSONL format."""
        from .chat_replay import download_chat

        download_chat(vod_id, dst_path)
        return dst_path


def normalise_chat_json(raw_comments: list[dict], dst_path: str) -> str:
    """Convert TwitchDownloader-style comment dicts to the pipeline's JSONL format."""
    with open(dst_path, "w") as f:
        for c in raw_comments:
            msg = ChatMessage(
                offset=float(c["content_offset_seconds"]),
                user=c.get("commenter", {}).get("display_name", ""),
                text=c.get("message", {}).get("body", ""),
            )
            f.write(json.dumps({"offset": msg.offset, "user": msg.user, "text": msg.text}) + "\n")
    return dst_path
