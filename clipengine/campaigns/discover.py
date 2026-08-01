"""Read-only Content Rewards discover-feed parser.

The flagship CPM campaigns are app/web-only (confirmed against production:
the REST API's /bounties is business-scoped), so automated discovery means
parsing the public discover page — squarely inside the brief's "read-only
campaign discovery" carve-out, and built defensively as the brief demands:
multiple extraction strategies, and graceful degradation to ``campaigns
add`` when the page structure changes.

Two input paths:
- live fetch (one GET with a browser user agent; the CDN may still refuse
  datacenter clients), or
- a page saved from the operator's browser (``--file``), which always works.

Strategies, tried in order:
1. Embedded JSON: campaign-like objects in script payloads (Next.js/RSC
   chunks), matched by reward-rate-ish keys with aliases.
2. Visible text: strip markup, find "$X / 1K"-style rates, then scan the
   surrounding lines for title, budget ("$X of $Y"), and platforms.
"""
from __future__ import annotations

import html as html_mod
import os
import re
from dataclasses import dataclass, field

import httpx

from .models import Campaign

# /discover/content-rewards/ redirects here (Content Rewards is a Whop app)
DISCOVER_URL = "https://whop.com/discover/app/app_QRxsQodZgK1r4D/"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

_PLATFORMS = ("tiktok", "youtube", "instagram", "facebook")


def _platforms_in(chunks: list[str]) -> list[str]:
    """Canonical platform names mentioned in the given text chunks.

    "x" needs care: as a substring it matches everything, so it only counts
    as Twitter/X when it stands alone (a chip label) or "twitter" appears.
    """
    found = []
    for p in _PLATFORMS:
        if any(p in c.lower() for c in chunks):
            found.append(p)
    if any("twitter" in c.lower() or c.strip().lower() in ("x", '"x"') for c in chunks):
        found.append("x")
    return found

# "$1.50 / 1K", "$1 per 1k views", "$0.50/1,000 views"
_RATE_RE = re.compile(
    r"\$\s*([\d][\d,]*\.?\d*)\s*(?:/|per)\s*1[,.]?0?0?0?\s*[Kk]?", re.I
)
# "$30,000 of $120,000", "$30K of $120K paid"
_OF_RE = re.compile(
    r"\$\s*([\d][\d,]*\.?\d*)\s*([KkMm])?\s*of\s*\$\s*([\d][\d,]*\.?\d*)\s*([KkMm])?"
)
_MONEY_KEY = r'"(?P<key>{})"\s*:\s*(?P<val>[\d.]+)'
_RATE_KEYS = ("rewardRate", "reward_rate", "cpm", "amountPerThousand",
              "rewardPerThousand", "costPerThousandViews")
_BUDGET_KEYS = ("totalBudget", "total_budget", "budgetAmount", "budget_amount", "budget")
_PAID_KEYS = ("paidOut", "paid_out", "totalPaid", "total_paid", "spent", "amountPaid")
_TITLE_RE = re.compile(r'"(?:title|name|campaignName)"\s*:\s*"((?:[^"\\]|\\.){3,120})"')


def _money(num: str, suffix: str | None) -> float:
    value = float(num.replace(",", ""))
    return value * {"k": 1e3, "m": 1e6}.get((suffix or "").lower(), 1.0)


@dataclass
class Discovered:
    title: str
    rate: float                    # $ per 1,000 verified views
    budget_total: float = 0.0
    budget_remaining: float = 0.0  # total - paid when both known, else total
    platforms: list[str] = field(default_factory=list)
    url: str = ""

    def to_campaign(self) -> Campaign:
        slug = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")[:48]
        return Campaign(
            id=f"disc:{slug}",
            source="manual",  # provenance: parsed from the web feed, not the API
            title=self.title,
            status="open",
            reward_model="cpm",
            reward_amount=self.rate,
            budget_total=self.budget_total,
            budget_remaining=self.budget_remaining or self.budget_total,
            platforms=self.platforms,
            url=self.url,
        )


def fetch_discover(url: str = DISCOVER_URL, client: httpx.Client | None = None) -> str:
    """One read-only GET with a browser UA. Raises httpx errors on refusal."""
    client = client or httpx.Client(timeout=30.0, follow_redirects=True)
    resp = client.get(url, headers={"User-Agent": BROWSER_UA,
                                    "Accept": "text/html,application/xhtml+xml"})
    resp.raise_for_status()
    return resp.text


def render_discover(url: str = DISCOVER_URL, wait_ms: int = 4000, scrolls: int = 4) -> str:
    """Render the page in headless Chromium and return the live DOM's HTML.

    The discover feed is client-rendered - the campaign cards exist only
    after the page's JavaScript runs, so a plain GET never sees them. This
    is still read-only discovery: a browser viewing the public page. Needs
    the optional dependency: pip install "clipengine[browser]" then
    'playwright install chromium'.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "browser rendering needs playwright: pip install 'clipengine[browser]' "
            "&& playwright install chromium"
        ) from e
    launch_opts: dict = {"headless": True}
    # explicit browser binary (e.g. a system Chromium, or a preinstalled
    # bundle whose revision differs from the pip playwright's expectation)
    exe = os.environ.get("CLIPENGINE_CHROMIUM_PATH")
    if exe:
        launch_opts["executable_path"] = exe
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(**launch_opts)
        except Exception as e:  # playwright's Error isn't importable cheaply
            if "xecutable doesn't exist" in str(e):
                raise RuntimeError(
                    "playwright is installed but its browser isn't - run: "
                    "playwright install chromium   (inside the same venv)"
                ) from e
            raise
        try:
            page = browser.new_page(user_agent=BROWSER_UA)
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(wait_ms)
            for _ in range(scrolls):  # trigger lazy-loading below the fold
                page.mouse.wheel(0, 2400)
                page.wait_for_timeout(900)
            # wait until money text exists in SOME frame (cards load late,
            # and Whop app content renders inside an iframe, not the page)
            for _ in range(20):
                if any("$" in (_frame_text(f) or "") for f in page.frames):
                    break
                page.wait_for_timeout(500)
            page.wait_for_timeout(800)
            return "\n".join(
                content for f in page.frames if (content := _frame_content(f))
            )
        finally:
            browser.close()


def _frame_text(frame) -> str:
    try:
        return frame.evaluate("document.body ? document.body.innerText : ''")
    except Exception:  # detached/navigating frames mid-render
        return ""


def _frame_content(frame) -> str:
    try:
        return frame.content()
    except Exception:
        return ""


def diagnose(html: str) -> str:
    """Compact report of what a page contains when no cards parsed -
    money-like tokens and structural markers, for tuning the patterns."""
    text_sample = re.findall(r"\$[0-9][0-9.,]*[^\"<>]{0,30}", html)[:8]
    markers = {
        "bytes": len(html),
        "__next_f": html.count("__next_f"),
        "__NEXT_DATA__": html.count("__NEXT_DATA__"),
        "bot check ('Just a moment')": len(re.findall(r"just a moment", html, re.I)),
        "rate keys": len(re.findall(_MONEY_KEY.format("|".join(_RATE_KEYS)),
                                    html.replace('\\"', '"'))),
        "'/ 1K' rate texts (anywhere)": len(_RATE_RE.findall(html)),
        # rates present only inside <script> = client-rendered: use --browser
        "'/ 1K' rate texts (visible)": len(_RATE_RE.findall(
            re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I))),
    }
    lines = [f"  {k}: {v}" for k, v in markers.items()]
    lines.append("  $-token samples: " + (" | ".join(text_sample) or "(none)"))
    return "\n".join(lines)


def parse_discover(html: str) -> list[Discovered]:
    found = _from_embedded_json(html)
    if not found:
        found = _from_split_cards(_visible_lines(html))
    if not found:
        found = _from_visible_text(html)
    return _dedupe(found)


def _nearest(window: str, pattern: re.Pattern, pos: int) -> re.Match | None:
    """The match whose position is closest to pos - adjacent campaign objects
    share extraction windows, so first-match grabs the neighbour's fields."""
    matches = list(pattern.finditer(window))
    return min(matches, key=lambda m: abs(m.start() - pos)) if matches else None


def _object_bounds(s: str, pos: int) -> tuple[int, int] | None:
    """Bounds of the JSON object enclosing pos, by brace matching - adjacent
    campaign objects are close together, so character windows bleed."""
    depth = 0
    start = -1
    for i in range(pos, -1, -1):
        c = s[i]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                start = i
                break
            depth -= 1
    if start < 0:
        return None
    depth = 0
    for j in range(start, min(len(s), start + 6000)):
        c = s[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, j + 1
    return None


def _from_embedded_json(html: str) -> list[Discovered]:
    """Campaign-like objects in script payloads, located by reward-rate keys."""
    # RSC chunks carry the JSON with escaped quotes (\"key\") - unescape once
    # up front so the locator and sub-searches see plain JSON either way
    html = html.replace('\\"', '"')
    rate_re = re.compile(_MONEY_KEY.format("|".join(_RATE_KEYS)))
    results = []
    for m in rate_re.finditer(html):
        bounds = _object_bounds(html, m.start())
        if bounds:
            window = html[bounds[0]: bounds[1]]
            pos = m.start() - bounds[0]
        else:
            start = max(0, m.start() - 800)
            window = html[start: m.end() + 800]
            pos = m.start() - start
        title_m = _nearest(window, _TITLE_RE, pos)
        if not title_m:
            continue
        budget = _nearest_key(window, _BUDGET_KEYS, pos)
        paid = _nearest_key(window, _PAID_KEYS, pos)
        remaining = max(0.0, budget - paid) if budget else 0.0
        title = title_m.group(1)
        try:
            title = title.encode().decode("unicode_escape")
        except UnicodeDecodeError:
            pass
        results.append(Discovered(
            title=title,
            rate=float(m.group("val")),
            budget_total=budget,
            budget_remaining=remaining,
            platforms=_platforms_in(re.findall(r'"([a-zA-Z]{1,12})"', window)),
            url=_nearby_url(window, pos),
        ))
    return results


def _nearest_key(window: str, keys: tuple[str, ...], pos: int) -> float:
    m = _nearest(window, re.compile(_MONEY_KEY.format("|".join(keys))), pos)
    return float(m.group("val")) if m else 0.0


def _nearby_url(window: str, pos: int) -> str:
    m = _nearest(
        window,
        re.compile(r'"(?:route|href|url|slug)"\s*:\s*"(/?[a-z0-9\-/]{3,80})"'),
        pos,
    )
    if not m:
        return ""
    path = m.group(1)
    return path if path.startswith("http") else f"https://whop.com/{path.lstrip('/')}"


# card chip labels that sit between the real title and the rate - never titles
_CHIP_LABELS = {
    "product", "technology", "personal brand", "music", "gaming", "health",
    "entertainment", "education", "finance", "sports", "software", "apps",
    "crypto", "fitness", "business", "lifestyle", "other", "clipping",
    "ugc", "faceless", "open", "active", "new", "slideshow", "content rewards",
}


def _visible_lines(html: str) -> list[str]:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    return [html_mod.unescape(ln.strip()) for ln in text.splitlines() if ln.strip()]


def card_contexts(html: str, before: int = 8, after: int = 9) -> list[list[str]]:
    """Raw line windows around each rate - the --debug view for parser tuning."""
    lines = _visible_lines(html)
    return [
        lines[max(0, i - before): i + after]
        for i, ln in enumerate(lines)
        if _RATE_RE.search(ln)
    ]


# the live feed's card anatomy (read from a real --debug run, 2026-08):
#   $2            <- rate amount, its own line
#   /1K           <- rate unit, its own line
#   Propaganda    <- community/brand name
#   ·
#   15d           <- age
#   Product       <- category chip
#   Pacinos UGC Clipping | $50k Budget | $1 CPM     <- title
#   Clip and post approved ... (description lines)
#   Join Campaign
#   $41,370       <- paid out so far
#   /$50,000      <- total budget
_AMOUNT_LINE = re.compile(r"^\$([\d][\d,]*\.?\d*)\s*([KkMm])?$")
_UNIT_LINE = re.compile(r"^/\s*1[,.]?0?0?0?\s*[Kk]?$")
_TOTAL_LINE = re.compile(r"^/\$([\d][\d,]*\.?\d*)\s*([KkMm])?$")
_AGE_LINE = re.compile(r"^\d+\s*(mo|[smhdwy])$")


def _from_split_cards(lines: list[str]) -> list[Discovered]:
    """The live feed's layout: every card field on its own text line."""
    results = []
    n = len(lines)
    for i, ln in enumerate(lines):
        m = _AMOUNT_LINE.match(ln)
        if not (m and i + 1 < n and _UNIT_LINE.match(lines[i + 1])):
            continue
        rate = _money(m.group(1), m.group(2))
        brand = lines[i + 2] if i + 2 < n and lines[i + 2] != "·" else ""
        join = next(
            (k for k in range(i + 2, min(i + 16, n))
             if lines[k].lower() == "join campaign"),
            None,
        )
        title = next(
            (lines[k] for k in range(i + 3, join if join is not None else min(i + 9, n))
             if lines[k] != "·"
             and not _AGE_LINE.match(lines[k])
             and lines[k].lower() not in _CHIP_LABELS),
            "",
        )
        if not title:
            continue
        paid = total = 0.0
        if join is not None:
            if join + 1 < n and (pm := _AMOUNT_LINE.match(lines[join + 1])):
                paid = _money(pm.group(1), pm.group(2))
            if join + 2 < n and (tm := _TOTAL_LINE.match(lines[join + 2])):
                total = _money(tm.group(1), tm.group(2))
        results.append(Discovered(
            title=f"{title} ({brand})" if brand else title,
            rate=rate,
            budget_total=total,
            budget_remaining=max(0.0, total - paid) if total else 0.0,
        ))
    return results


def _from_visible_text(html: str) -> list[Discovered]:
    """Strip markup, then read card text around each '$X / 1K' occurrence."""
    lines = _visible_lines(html)
    results = []
    for i, line in enumerate(lines):
        rate_m = _RATE_RE.search(line)
        if not rate_m:
            continue
        title = next(
            (ln for ln in reversed(lines[max(0, i - 5): i])
             if 3 <= len(ln) <= 90 and not any(c in ln for c in "$%")
             and not _RATE_RE.search(ln)
             and ln.lower() not in _PLATFORMS
             and ln.lower().strip() not in _CHIP_LABELS
             and not ln.lower().startswith(("clipping campaign", "ugc campaign", "view "))),
            "",
        )
        if not title:
            continue
        # a card's own budget/platform chips follow its rate line; search
        # forward first so the previous card's lines can't be picked up
        card_lines = lines[i: i + 5] + lines[max(0, i - 2): i]
        budget_total = remaining = 0.0
        for ln in card_lines:
            of_m = _OF_RE.search(ln)
            if of_m:
                paid = _money(of_m.group(1), of_m.group(2))
                budget_total = _money(of_m.group(3), of_m.group(4))
                remaining = max(0.0, budget_total - paid)
                break
        results.append(Discovered(
            title=title,
            rate=float(rate_m.group(1).replace(",", "")),
            budget_total=budget_total,
            budget_remaining=remaining,
            platforms=_platforms_in(card_lines),
        ))
    return results


def _dedupe(items: list[Discovered]) -> list[Discovered]:
    seen: dict[tuple, Discovered] = {}
    for item in items:
        seen.setdefault((item.title.lower(), item.rate), item)
    return list(seen.values())
