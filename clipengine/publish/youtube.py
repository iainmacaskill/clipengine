"""YouTube Shorts publishing. Status: stub.

Route: YouTube Data API v3 `videos.insert` with OAuth per channel. Shorts are
regular uploads that are vertical and <=3min; include #Shorts in the title/description.
Planned in Phase 2 (see product plan section 7); MVP exports files for manual upload.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UploadRequest:
    video_path: str
    title: str
    description: str
    tags: list[str]
    channel_id: str


def upload(req: UploadRequest) -> str:
    """Upload a video, returning the YouTube video ID."""
    raise NotImplementedError("YouTube upload lands in Phase 2 - MVP exports for manual upload")
