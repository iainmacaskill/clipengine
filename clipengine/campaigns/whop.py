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

Production reality check (first real sync, 2026-08-01): the live API 404s
``/workforce/bounties`` — that surface is in the SDK but not yet rolled out.
The original ``GET /bounties`` surface is the fallback (different vocabulary,
translated in ``_from_legacy``); the client tries workforce first so it
upgrades automatically when Whop ships it.

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
APP_ID_ENVS = ("CLIPENGINE_WHOP_APP_ID", "WHOP_APP_ID")
API_VERSION = "2026-07-08-1"  # the SDK's default Api-Version-Date - sent always


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
        base_url: str | None = None,
        app_id: str | None = None,
    ):
        if not api_key:
            raise WhopError(
                "Whop API key required: set CLIPENGINE_WHOP_API_KEY (or WHOP_API_KEY). "
                "The API authenticates apps - create one in the Whop dashboard's "
                "developer section and use its App API key (+ WHOP_APP_ID)."
            )
        # WHOP_BASE_URL override mirrors the official SDK (test/staging endpoints)
        self._base = (base_url or os.environ.get("WHOP_BASE_URL") or BASE_URL).rstrip("/")
        self._client = client or httpx.Client(timeout=30.0)
        # header set mirrors the SDK: Api-Version-Date always; app id when known
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Api-Version-Date": API_VERSION,
        }
        if app_id is None:
            app_id = next((os.environ[e] for e in APP_ID_ENVS if os.environ.get(e)), None)
        if app_id:
            self._headers["X-Whop-App-Id"] = app_id

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._client.get(self._base + path, params=params, headers=self._headers)
        if resp.status_code >= 400:
            raise WhopError(f"GET {path} failed: {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def _paged(self, path: str, params: dict, page_size: int, max_pages: int) -> list[dict]:
        items: list[dict] = []
        after: str | None = None
        for _ in range(max_pages):
            page_params = dict(params, first=page_size)
            if after:
                page_params["after"] = after
            page = self._get(path, page_params)
            items.extend(page.get("data") or [])
            after = (page.get("page_info") or {}).get("end_cursor")
            if not after:
                break
        return items

    def list_bounties(
        self, status: str = "open", page_size: int = 50, max_pages: int = 20
    ) -> list[dict]:
        """All bounties with the given status, raw, following cursor pagination.

        Tries the richer ``/workforce/bounties`` surface first; production
        404s it as of 2026-08 (staged rollout — first real sync confirmed),
        so on 404 this falls back to the original ``/bounties`` surface and
        translates its vocabulary to the workforce shape. Legacy items carry
        no ``business_goal_type`` key (the read model doesn't expose it), no
        per-submission reward, and their ``description`` inline.
        """
        try:
            return self._paged(
                "/workforce/bounties",
                {"status": status, "order": "created_at", "direction": "desc"},
                page_size, max_pages,
            )
        except WhopError as e:
            if " 404 " not in str(e):
                raise
        legacy = self._paged(
            "/bounties",
            {"status": _LEGACY_STATUS.get(status, status)},
            page_size, max_pages,
        )
        return [_from_legacy(raw) for raw in legacy]

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
            # legacy /bounties items don't expose a goal type at all - the
            # filter would drop everything, so it only applies when the key
            # exists (workforce surface); legacy items pass through for the
            # operator/scoring to judge
            if goal_types is not None and "business_goal_type" in raw:
                if (raw.get("business_goal_type") or "") not in goal_types:
                    continue
            rules = raw.get("description") or ""
            if with_rules and not rules:
                try:
                    rules = self.bounty(raw["id"]).get("description") or ""
                except (WhopError, httpx.HTTPError):
                    pass
            campaigns.append(_normalise(raw, rules))
        return campaigns


# original /bounties surface <-> canonical status vocabulary
_LEGACY_STATUS = {"open": "published", "closed": "archived"}
_LEGACY_TO_CANON = {"published": "open", "archived": "closed"}


def _from_legacy(raw: dict) -> dict:
    """Translate an original-surface /bounties item to the workforce shape.

    total_available is the remaining pool and total_paid what's gone out;
    per-submission reward and goal type aren't in this read model (the create
    params prove the server knows them - the serializer just omits them), so
    reward stays 0 and the business_goal_type key is deliberately absent.
    """
    available = float(raw.get("total_available") or 0.0)
    paid = float(raw.get("total_paid") or 0.0)
    status = raw.get("status") or ""
    return {
        "id": raw.get("id") or "",
        "title": raw.get("title") or "",
        "status": _LEGACY_TO_CANON.get(status, status),
        "currency": raw.get("currency") or "usd",
        "budget_amount": available + paid,
        "gross_paid_out_amount": paid,
        "gross_reward_amount": 0.0,
        "description": raw.get("description") or "",
        "created_at": str(raw.get("created_at") or ""),
    }


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
