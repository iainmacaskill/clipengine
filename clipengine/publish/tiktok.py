"""TikTok publishing. Status: stub.

Route: TikTok Content Posting API (requires an audited developer app - the audit
has the longest external lead time in the project; submit early). Until approval,
the pipeline exports TikTok-ready files for manual upload.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PostRequest:
    video_path: str
    caption: str
    account_id: str


def post(req: PostRequest) -> str:
    """Post a video, returning the TikTok post ID."""
    raise NotImplementedError("TikTok Content Posting API pending app audit - export manually")
