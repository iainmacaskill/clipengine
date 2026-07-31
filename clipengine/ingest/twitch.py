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

    def download_vod(self, vod_id: str, dst_path: str) -> str:
        """Download a VOD's video. TODO.

        Routes, in preference order:
        1. streamer-authorised download via their own OAuth grant (Model A/C opt-in)
        2. yt-dlp against the VOD URL (simplest; respects sub-only restrictions)
        """
        raise NotImplementedError("VOD download not implemented yet")

    def download_chat(self, vod_id: str, dst_path: str) -> str:
        """Download the VOD chat replay and normalise to JSONL. TODO.

        Twitch's chat replay is served via an undocumented GQL endpoint; established
        open-source tooling (e.g. TwitchDownloader chat mode) is the pragmatic route.
        Normalise into the JSONL shape parse_chat_jsonl expects.
        """
        raise NotImplementedError("chat download not implemented yet")


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
