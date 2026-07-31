"""VOD chat replay downloader.

Twitch has no official Helix endpoint for chat replay; like established tooling
(TwitchDownloader et al.) this uses the public web client's GQL persisted query
`VideoCommentsByOffsetOrCursor`. Two operational notes:

- ``PERSISTED_QUERY_HASH`` is a constant belonging to the Twitch web client. It
  changes occasionally; if requests start failing with ``PersistedQueryNotFound``,
  refresh the hash from the web client's network traffic (or TwitchDownloader's
  source, which tracks it).
- Only download chat for streamers on the permission roster (product plan §2).
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterator

import httpx

from ..models import ChatMessage

GQL_URL = "https://gql.twitch.tv/gql"
# public client-id of Twitch's own web player (not a secret)
PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
PERSISTED_QUERY_HASH = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"

_PAGE_PAUSE_S = 0.1  # politeness delay between pages
_MAX_RETRIES = 4


class ChatReplayError(RuntimeError):
    pass


def _gql_request(
    client: httpx.Client, video_id: str, *, cursor: str | None, offset: float
) -> dict:
    variables: dict = {"videoID": video_id}
    if cursor:
        variables["cursor"] = cursor
    else:
        variables["contentOffsetSeconds"] = int(offset)
    payload = {
        "operationName": "VideoCommentsByOffsetOrCursor",
        "variables": variables,
        "extensions": {
            "persistedQuery": {"version": 1, "sha256Hash": PERSISTED_QUERY_HASH}
        },
    }
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.post(
                GQL_URL,
                json=payload,
                headers={"Client-ID": PUBLIC_CLIENT_ID, "Content-Type": "application/json"},
            )
            if resp.status_code >= 500:
                raise ChatReplayError(f"GQL server error {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            errors = data.get("errors")
            if errors:
                raise ChatReplayError(f"GQL errors: {errors}")
            return data
        except (httpx.TransportError, ChatReplayError) as e:
            last_error = e
            time.sleep(2**attempt)
    raise ChatReplayError(f"chat replay request failed after {_MAX_RETRIES} retries: {last_error}")


def _parse_comment(node: dict) -> ChatMessage:
    commenter = node.get("commenter") or {}  # null for deleted accounts
    fragments = (node.get("message") or {}).get("fragments") or []
    text = "".join(f.get("text", "") for f in fragments)
    return ChatMessage(
        offset=float(node.get("contentOffsetSeconds", 0)),
        user=commenter.get("displayName") or "",
        text=text,
    )


def iter_chat(
    video_id: str,
    client: httpx.Client | None = None,
    start_offset: float = 0.0,
    page_pause_s: float = _PAGE_PAUSE_S,
) -> Iterator[ChatMessage]:
    """Yield every chat message of a VOD in timeline order, paginating by cursor."""
    own_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        cursor: str | None = None
        first_page = True
        while True:
            data = _gql_request(client, video_id, cursor=cursor, offset=start_offset)
            video = (data.get("data") or {}).get("video")
            if video is None:
                raise ChatReplayError(
                    f"no video {video_id} (deleted, sub-only, or chat unavailable)"
                )
            comments = video.get("comments") or {}
            edges = comments.get("edges") or []
            for edge in edges:
                yield _parse_comment(edge.get("node") or {})
            has_next = (comments.get("pageInfo") or {}).get("hasNextPage", False)
            if not has_next or not edges:
                return
            cursor = edges[-1].get("cursor")
            if not cursor:
                return
            if not first_page and page_pause_s:
                time.sleep(page_pause_s)
            first_page = False
    finally:
        if own_client:
            client.close()


def download_chat(
    video_id: str,
    dst_path: str,
    client: httpx.Client | None = None,
    progress_every: int = 5000,
) -> int:
    """Download a VOD's full chat replay to the pipeline's JSONL format.

    Returns the number of messages written. Output lines match what
    detect.chat.parse_chat_jsonl expects: {"offset": s, "user": u, "text": t}.
    """
    count = 0
    with open(dst_path, "w") as f:
        for msg in iter_chat(video_id, client=client):
            f.write(
                json.dumps({"offset": msg.offset, "user": msg.user, "text": msg.text}) + "\n"
            )
            count += 1
            if progress_every and count % progress_every == 0:
                print(f"  chat: {count} messages (t={msg.offset:.0f}s)")
    return count
