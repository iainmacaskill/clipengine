"""Webhook launch alerts for high-value campaigns.

Budget pools are first-come-first-served, so the M1 target is an alert within
15 minutes of a campaign launching (dev brief §6). Payload is
Discord-compatible (``{"content": ...}``); any receiver accepting that JSON
shape works (Discord webhook, Slack via bridge, self-hosted).
"""
from __future__ import annotations

import httpx

from .score import ScoredCampaign


def format_alert(scored: list[ScoredCampaign]) -> str:
    lines = ["**New campaigns**"]
    for s in scored:
        c = s.campaign
        reward = (
            f"{c.reward_amount:g} {c.currency}/1k views"
            if c.reward_model == "cpm"
            else f"{c.reward_amount:g} {c.currency}/submission"
        )
        lines.append(
            f"- [{s.score:.1f}] {c.title} ({c.brand or c.source}) — {reward}, "
            f"{c.budget_remaining:g} {c.currency} remaining, "
            f"{s.checklist.complexity} rule items — {c.url or c.id}"
        )
    return "\n".join(lines)


def notify(
    webhook_url: str,
    scored: list[ScoredCampaign],
    client: httpx.Client | None = None,
) -> bool:
    """POST the alert; returns success. Alert failure must never fail a sync."""
    if not webhook_url or not scored:
        return False
    client = client or httpx.Client(timeout=10.0)
    try:
        resp = client.post(webhook_url, json={"content": format_alert(scored)})
        return resp.status_code < 300
    except httpx.HTTPError:
        return False
