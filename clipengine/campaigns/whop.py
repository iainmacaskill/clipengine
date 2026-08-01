"""Read-only Whop Workforce Bounties client.

Endpoint shapes verified against the official SDK (whop-sdk 0.0.41, Stainless
generated from Whop's OpenAPI spec):

- base URL ``https://api.whop.com/api/v1``, ``Authorization: Bearer <key>``
- ``GET /workforce/bounties`` — cursor pagination: response is
  ``{"data": [...], "page_info": {"end_cursor": ...}}``, next page via
  ``after=<end_cursor>``. Filters: ``status``, ``first``, ``order``,
  ``direction``, ``query``, created-date window. There is NO server-side
  ``business_goal_type`` filter — filtering happens client-side here.
- ``GET /workforce/bounties/{id}`` — adds ``description`` (the rules text),
  absent from list items.
- ``GET /payouts`` (exactly one of ``user_id``/``account_id``; same cursor
  envelope) and ``GET /ledger_accounts/{id}`` — the balance/withdrawal side,
  used by the submission tracker's reconciliation step.

This client only ever issues GET requests — read-only campaign discovery is
the hard boundary set in the dev brief (§4). The CPM-per-views Content
Rewards campaigns are not in the public API at all; those enter the store
via manual entry (``clipengine campaigns add``).
"""
from __future__ import annotations

import os

import httpx

from .models import REWARD_PER_SUBMISSION, Campaign

BASE_URL = "https://api.whop.com/api/v1"
DEFAULT_GOAL_TYPES = ("clipping", "ugc_content")
API_KEY_ENVS = ("CLIPENGINE_WHOP_API_KEY", "WHOP_API_KEY")


class WhopError(RuntimeError):
    pass


def api_key_from_env() -> str:
    for name in API_KEY_ENVS:
        key = os.environ.get(name, "")
        if key:
            return key
    return ""


class WhopClient:
    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        base_url: str = BASE_URL,
    ):
        if not api_key:
            raise WhopError(
                "Whop API key required: set CLIPENGINE_WHOP_API_KEY (or WHOP_API_KEY)"
            )
        self._base = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=30.0)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._client.get(self._base + path, params=params, headers=self._headers)
        if resp.status_code >= 400:
            raise WhopError(f"GET {path} failed: {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def list_bounties(
        self, status: str = "open", page_size: int = 50, max_pages: int = 20
    ) -> list[dict]:
        """All bounties with the given status, raw, following cursor pagination."""
        items: list[dict] = []
        after: str | None = None
        for _ in range(max_pages):
            params: dict = {"status": status, "first": page_size,
                            "order": "created_at", "direction": "desc"}
            if after:
                params["after"] = after
            page = self._get("/workforce/bounties", params)
            items.extend(page.get("data") or [])
            after = (page.get("page_info") or {}).get("end_cursor")
            if not after:
                break
        return items

    def bounty(self, bounty_id: str) -> dict:
        return self._get(f"/workforce/bounties/{bounty_id}")

    def payouts(
        self,
        user_id: str | None = None,
        account_id: str | None = None,
        page_size: int = 50,
        max_pages: int = 20,
    ) -> list[dict]:
        """Withdrawal requests (amount/status/created_at), for reconciliation.

        The API requires exactly one of user_id or account_id.
        """
        if bool(user_id) == bool(account_id):
            raise WhopError("pass exactly one of user_id or account_id")
        items: list[dict] = []
        after: str | None = None
        for _ in range(max_pages):
            params: dict = {"first": page_size}
            params["user_id" if user_id else "account_id"] = user_id or account_id
            if after:
                params["after"] = after
            page = self._get("/payouts", params)
            items.extend(page.get("data") or [])
            after = (page.get("page_info") or {}).get("end_cursor")
            if not after:
                break
        return items

    def ledger_account(self, ledger_account_id: str) -> dict:
        """Balance state (balance / pending_balance / currency) for reconciliation."""
        return self._get(f"/ledger_accounts/{ledger_account_id}")

    def campaigns(
        self,
        status: str = "open",
        goal_types: tuple[str, ...] | None = DEFAULT_GOAL_TYPES,
        with_rules: bool = True,
        max_pages: int = 20,
    ) -> list[Campaign]:
        """Discover bounty campaigns as normalised Campaign records.

        ``with_rules`` fetches each bounty's detail for its description (the
        rules text) — one extra GET per campaign; a failed detail fetch keeps
        the campaign with empty rules rather than dropping it.
        """
        campaigns = []
        for raw in self.list_bounties(status=status, max_pages=max_pages):
            goal = raw.get("business_goal_type") or ""
            if goal_types is not None and goal not in goal_types:
                continue
            rules = ""
            if with_rules:
                try:
                    rules = self.bounty(raw["id"]).get("description") or ""
                except (WhopError, httpx.HTTPError):
                    pass
            campaigns.append(_normalise(raw, rules))
        return campaigns


def _normalise(raw: dict, rules_text: str = "") -> Campaign:
    budget = float(raw.get("budget_amount") or 0.0)
    paid = float(raw.get("gross_paid_out_amount") or 0.0)
    funding = raw.get("funding_account") or {}
    poster = raw.get("poster") or {}
    return Campaign(
        id=raw["id"],
        source="whop_bounty",
        title=raw.get("title") or "",
        brand=funding.get("title") or poster.get("username") or "",
        goal_type=raw.get("business_goal_type") or "",
        status=raw.get("status") or "",
        currency=raw.get("currency") or "usd",
        reward_model=REWARD_PER_SUBMISSION,
        reward_amount=float(raw.get("gross_reward_amount") or 0.0),
        budget_total=budget,
        budget_remaining=max(0.0, budget - paid),
        spots_remaining=raw.get("spots_remaining"),
        paid_out=paid,
        unresolved=int(raw.get("unresolved_submissions_count") or 0),
        rules_text=rules_text,
        created_at=raw.get("created_at") or "",
    )
