"""JSON API logic for the web UI.

Every function here maps to one screen action and calls the existing engine
modules - campaigns store/score/rules/template/gate, pipeline, submissions.
The HTTP layer (server.py) only does routing and (de)serialisation; keeping
the logic here as plain functions means the tests exercise it without a socket.

Functions return (status_code, body_dict). The three long ones - prepare,
detect, render - return a job immediately and do their work on a thread.
"""
from __future__ import annotations

import os

from ..config import Config
from ..edit import textcard
from .jobs import Job, JobRegistry
from .store import SourceStore

# ---- media/db locations (derived from the campaigns DB dir) ----------------


def _base_dir(cfg: Config) -> str:
    return os.path.dirname(cfg.campaigns.campaigns_db) or "."


def sources_db_path(cfg: Config) -> str:
    return os.path.join(_base_dir(cfg), "sources.db")


def media_dir(cfg: Config, campaign_id: str) -> str:
    from ..campaigns.models import slugify

    d = os.path.join(_base_dir(cfg), "media", slugify(campaign_id))
    os.makedirs(d, exist_ok=True)
    return d


# ---- serialisers -----------------------------------------------------------


def _campaign_dict(scored) -> dict:
    c = scored.campaign
    return {
        "id": c.id,
        "title": c.title,
        "brand": c.brand,
        "status": c.status,
        "reward_model": c.reward_model,
        "reward_amount": c.reward_amount,
        "currency": c.currency,
        "reward_str": c.reward_str,
        "budget_total": c.budget_total,
        "budget_remaining": c.budget_remaining,
        "platforms": c.platforms,
        "url": c.url,
        "score": round(scored.score, 2),
        "score_breakdown": scored.breakdown,
    }


def checklist_dict(check) -> dict:
    """The parsed rules, shaped for the 'rules translated' screen."""
    return {
        "hashtags": check.hashtags,
        "mentions": check.mentions,
        "min_duration_s": check.min_duration_s,
        "max_duration_s": check.max_duration_s,
        "platforms": check.platforms,
        "required": check.required,
        "banned": check.banned,
        "links": check.links,
        "complexity": check.complexity,
    }


# ---- campaigns -------------------------------------------------------------


def list_campaigns(cfg: Config) -> tuple[int, dict]:
    from ..campaigns.score import rank
    from ..campaigns.store import CampaignStore

    with CampaignStore(cfg.campaigns.campaigns_db) as store:
        scored = rank(store.list(), cfg.campaigns.familiarity)
    return 200, {"campaigns": [_campaign_dict(s) for s in scored]}


def get_campaign(cfg: Config, campaign_id: str) -> tuple[int, dict]:
    from ..campaigns.score import score_campaign
    from ..campaigns.store import CampaignStore
    from ..campaigns.template import template_for

    with CampaignStore(cfg.campaigns.campaigns_db) as store:
        campaign = store.get(campaign_id)
    if campaign is None:
        return 404, {"error": f"no campaign {campaign_id}"}
    scored = score_campaign(campaign, cfg.campaigns.familiarity)
    template = template_for(campaign)
    return 200, {
        **_campaign_dict(scored),
        "rules_text": campaign.rules_text,
        "checklist": checklist_dict(scored.checklist),
        "caption_suffix": template.caption_suffix,
        "credit_text": template.credit_text,
    }


def add_campaign(cfg: Config, payload: dict) -> tuple[int, dict]:
    from ..campaigns.models import Campaign, slugify
    from ..campaigns.score import score_campaign
    from ..campaigns.store import CampaignStore

    title = (payload.get("title") or "").strip()
    if not title:
        return 400, {"error": "title is required"}
    cid = (payload.get("id") or f"manual:{slugify(title)}").strip()
    try:
        cpm = float(payload.get("cpm", 0) or 0)
        budget = float(payload.get("budget", 0) or 0)
    except (TypeError, ValueError):
        return 400, {"error": "cpm and budget must be numbers"}
    remaining = payload.get("remaining")
    campaign = Campaign(
        id=cid, source="manual", title=title,
        brand=(payload.get("brand") or "").strip(),
        goal_type=payload.get("goal") or "clipping",
        status="open", currency=payload.get("currency") or "usd",
        reward_model="cpm", reward_amount=cpm,
        budget_total=budget,
        budget_remaining=float(remaining) if remaining not in (None, "") else budget,
        platforms=[p.strip() for p in (payload.get("platforms") or "").split(",") if p.strip()],
        rules_text=payload.get("rules_text") or "",
        url=payload.get("url") or "",
    )
    with CampaignStore(cfg.campaigns.campaigns_db) as store:
        store.upsert([campaign])
    scored = score_campaign(campaign, cfg.campaigns.familiarity)
    return 201, _campaign_dict(scored)


# ---- sources ---------------------------------------------------------------


def _approved_links(cfg: Config, campaign_id: str) -> list[str]:
    from ..campaigns.rules import parse_rules
    from ..campaigns.store import CampaignStore

    with CampaignStore(cfg.campaigns.campaigns_db) as store:
        campaign = store.get(campaign_id)
    return parse_rules(campaign.rules_text).links if campaign else []


def _link_allowed(url: str, approved: list[str]) -> bool:
    from ..campaigns.gate import _norm_url

    if not approved:
        return True  # campaign lists no explicit sources - nothing to enforce
    u = _norm_url(url)
    return any(_norm_url(a) in u or u in _norm_url(a) for a in approved)


def list_sources(cfg: Config, store: SourceStore, campaign_id: str) -> tuple[int, dict]:
    return 200, {"sources": [s.to_dict() for s in store.list(campaign_id)]}


def add_source(cfg: Config, store: SourceStore, payload: dict) -> tuple[int, dict]:
    campaign_id = (payload.get("campaign_id") or "").strip()
    url = (payload.get("url") or "").strip()
    path = (payload.get("path") or "").strip()
    if not campaign_id:
        return 400, {"error": "campaign_id is required"}
    if url and not _link_allowed(url, _approved_links(cfg, campaign_id)):
        return 400, {
            "error": "that link isn't on this campaign's approved-source list - "
            "clipping it would get the post rejected",
            "approved": _approved_links(cfg, campaign_id),
        }
    try:
        source = store.add(campaign_id, url=url, path=path,
                           title=payload.get("title") or "")
    except ValueError as e:
        return 400, {"error": str(e)}
    return 201, source.to_dict()


# ---- long jobs: prepare (download + transcribe) ----------------------------

# Injection seams so tests don't need yt-dlp / whisper / ffmpeg.


def download_source(url: str, dest_dir: str) -> str:
    """Download a source video with yt-dlp; return the local path."""
    try:
        import yt_dlp
    except ImportError as e:
        raise RuntimeError(
            "downloading links needs yt-dlp - install clipengine[download], "
            "or add the file directly instead of a link"
        ) from e
    opts = {
        "outtmpl": os.path.join(dest_dir, "%(id)s.%(ext)s"),
        "format": "mp4/bestvideo+bestaudio/best",
        "quiet": True, "noprogress": True, "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)


def job_prepare_source(cfg: Config, sources_path: str, source_id: int):
    """Return a job function: download (if a link) then transcribe once.

    Opens its OWN SourceStore inside the job so the sqlite connection lives on
    the thread that uses it (jobs run on a background thread, not the request
    thread that created them)."""
    from .. import pipeline
    from ..edit import ffmpeg as edit

    def run(job: Job):
        store = SourceStore(sources_path)
        try:
            source = store.get(source_id)
            path = source.path
            if not path and source.url:
                store.update(source_id, status="downloading")
                job.update(0.1, "downloading video")
                path = download_source(source.url, media_dir(cfg, source.campaign_id))
                store.update(source_id, path=path)
            if not path or not os.path.exists(path):
                raise RuntimeError(
                    "source file is missing - add the file or a valid link"
                )
            probe = edit.probe(path)
            store.update(source_id, status="transcribing", duration_s=probe.duration)
            job.update(0.4, "transcribing (once - then reused for every clip)")
            pipeline.source_transcript(path, cfg)  # caches beside the file
            store.update(source_id, status="ready",
                         detail=f"{probe.width}x{probe.height}, {probe.duration:.0f}s")
            job.update(1.0, "ready")
            return store.get(source_id).to_dict()
        finally:
            store.close()

    return run


# ---- long jobs: detect (find moments) --------------------------------------


def job_detect(cfg: Config, sources_path: str, source_id: int, top: int = 8):
    from .. import pipeline

    def run(job: Job):
        store = SourceStore(sources_path)
        try:
            source = store.get(source_id)
        finally:
            store.close()
        if not source.path or not os.path.exists(source.path):
            raise RuntimeError("prepare the source first (download + transcribe)")
        job.update(0.2, "scanning for the hottest moments")
        candidates = pipeline.detect_candidates(source.path, None, cfg)[:top]
        job.update(0.7, "reading what's said in each window")
        transcript = pipeline.source_transcript(source.path, cfg)
        moments = []
        for c in candidates:
            excerpt = transcript.text_between(c.start, c.end).strip()
            moments.append({
                "start": round(c.start, 1),
                "end": round(c.end, 1),
                "score": round(c.score, 3),
                "excerpt": excerpt[:400],
            })
        return {"source_id": source_id, "moments": moments}

    return run


# ---- long jobs: render a batch of clips ------------------------------------


def _render_one(cfg: Config, store: SourceStore, clip: dict) -> dict:
    from .. import pipeline
    from ..campaigns.gate import ClipFacts, preflight
    from ..campaigns.rules import parse_rules
    from ..campaigns.store import CampaignStore
    from ..campaigns.template import build_caption, merge_credit, template_for

    source = store.get(int(clip["source_id"]))
    campaign_id = source.campaign_id
    with CampaignStore(cfg.campaigns.campaigns_db) as cstore:
        campaign = cstore.get(campaign_id)
    template = template_for(campaign) if campaign else None
    checklist = parse_rules(campaign.rules_text) if campaign else None

    start = float(clip["start"])
    end = float(clip["end"])
    hook = clip.get("hook") or None
    style = clip.get("style") or "clean"
    caption = clip.get("caption") or ""
    if template is not None:
        caption = build_caption(caption, template)
    credit = merge_credit("", template) if template else ""

    out_dir = media_dir(cfg, campaign_id)
    out_path = os.path.join(out_dir, f"{clip.get('out_name') or 'clip'}.mp4")

    transcript = pipeline.source_transcript(source.path, cfg)
    snapped_start, snapped_end = pipeline.snap_to_speech(transcript, start, end)
    pipeline.repurpose_asset(
        source.path, out_path, cfg,
        hook=hook, credit_text=credit or None,
        start=snapped_start, end=snapped_end,
        with_captions=True, style=style, transcript=transcript,
    )
    report = None
    if campaign is not None and checklist is not None:
        report = preflight(
            ClipFacts(
                duration_s=snapped_end - snapped_start,
                caption=caption, credit_text=credit,
                platform=clip.get("platform") or "",
                source_url=source.url,
            ),
            checklist, campaign,
        )
    return {
        "out_name": clip.get("out_name"),
        "path": out_path,
        "caption": caption,
        "start": snapped_start, "end": snapped_end,
        "style": style,
        "gate": None if report is None else {
            "passed": report.passed,
            "failures": [r.detail for r in report.failures],
            "manual": [r.detail for r in report.manual],
        },
    }


def job_render(cfg: Config, sources_path: str, clips: list[dict]):
    def run(job: Job):
        store = SourceStore(sources_path)  # own connection on the job thread
        results = []
        n = max(1, len(clips))
        try:
            for i, clip in enumerate(clips):
                job.update(i / n, f"rendering clip {i + 1} of {len(clips)}")
                try:
                    results.append(_render_one(cfg, store, clip))
                except Exception as e:  # noqa: BLE001 - one clip's failure isn't fatal
                    results.append({
                        "out_name": clip.get("out_name"),
                        "error": f"{type(e).__name__}: {str(e)[:200]}",
                    })
        finally:
            store.close()
        return {"clips": results}

    return run


# ---- submissions -----------------------------------------------------------


def list_submissions(cfg: Config, campaign_id: str | None = None) -> tuple[int, dict]:
    from ..campaigns.submissions import SubmissionStore

    with SubmissionStore(cfg.campaigns.campaigns_db) as store:
        subs = store.list(campaign_id=campaign_id)
    return 200, {"submissions": [_submission_dict(s) for s in subs]}


def add_submission(cfg: Config, payload: dict) -> tuple[int, dict]:
    from ..campaigns.submissions import SubmissionStore

    campaign_id = (payload.get("campaign_id") or "").strip()
    post_url = (payload.get("post_url") or "").strip()
    if not campaign_id or not post_url:
        return 400, {"error": "campaign_id and post_url are required"}
    with SubmissionStore(cfg.campaigns.campaigns_db) as store:
        try:
            sub = store.add(
                campaign_id, post_url,
                platform=payload.get("platform") or "",
                account=payload.get("account") or "",
                title=payload.get("title") or "",
            )
        except ValueError as e:
            return 400, {"error": str(e)}
    return 201, _submission_dict(sub)


def _submission_dict(s) -> dict:
    return {
        "id": s.id, "campaign_id": s.campaign_id, "post_url": s.post_url,
        "platform": s.platform, "status": s.status, "views": s.views,
        "amount": s.amount, "submitted_at": s.submitted_at,
    }


# ---- style presets (for the clip builder) ----------------------------------


def list_presets() -> tuple[int, dict]:
    return 200, {"presets": sorted(textcard.PRESETS)}


# ---- job polling -----------------------------------------------------------


def get_job(registry: JobRegistry, job_id: str) -> tuple[int, dict]:
    job = registry.get(job_id)
    if job is None:
        return 404, {"error": f"no job {job_id}"}
    return 200, job.to_dict()
