"""clipengine CLI.

  clipengine detect  VIDEO [--chat chat.jsonl]     -> ranked candidate windows (JSON)
  clipengine render  VIDEO --start S --end E --facecam X,Y,W,H -o OUT  -> final clip
  clipengine vods    STREAMER_LOGIN                -> recent VODs (needs Twitch creds)
"""
from __future__ import annotations

import argparse
import json
import sys

from . import config, pipeline
from .models import ClipCandidate, FacecamRegion


def _cmd_detect(args: argparse.Namespace, cfg: config.Config) -> int:
    candidates = pipeline.detect_candidates(args.video, args.chat, cfg)
    out = [
        {
            "start": round(c.start, 2),
            "end": round(c.end, 2),
            "score": round(c.score, 3),
            "signals": {k: round(v, 3) for k, v in c.signal_breakdown.items()},
        }
        for c in candidates
    ]
    json.dump(out, sys.stdout, indent=1)
    print()
    return 0


def _cmd_render(args: argparse.Namespace, cfg: config.Config) -> int:
    from .pipeline import credit_text_for

    credit: str | None = None
    if args.credit:
        credit = args.credit
    elif args.streamer:
        from .roster import Roster

        with Roster(cfg.roster_db) as roster:
            entry = roster.require(args.streamer)
        credit = credit_text_for(args.streamer, entry.credit)
    elif not args.no_credit:
        print(
            "credit required: pass --streamer LOGIN (uses their roster credit format), "
            "--credit TEXT, or --no-credit for private test renders",
            file=sys.stderr,
        )
        return 1
    if args.facecam:
        x, y, w, h = (int(v) for v in args.facecam.split(","))
        facecam = FacecamRegion(x, y, w, h)
    else:
        from .edit.facecam import detect_facecam

        found = detect_facecam(args.video)
        if found is None:
            print(
                "no facecam detected - pass --facecam X,Y,W,H explicitly",
                file=sys.stderr,
            )
            return 1
        facecam = found.region
        print(
            f"facecam auto-detected: {facecam.x},{facecam.y},{facecam.w},{facecam.h} "
            f"(score {found.score:.2f})",
            file=sys.stderr,
        )
    if args.campaign:
        from .campaigns.store import CampaignStore
        from .campaigns.template import merge_credit, template_for

        with CampaignStore(cfg.campaigns.campaigns_db) as store:
            campaign_rec = store.get(args.campaign)
        if campaign_rec is None:
            print(f"unknown campaign: {args.campaign}", file=sys.stderr)
            return 1
        template = template_for(campaign_rec)
        credit = merge_credit(credit or "", template) or None
        duration = args.end - args.start
        for bound, ok in (
            (template.min_duration_s, template.min_duration_s is None
             or duration >= template.min_duration_s),
            (template.max_duration_s, template.max_duration_s is None
             or duration <= template.max_duration_s),
        ):
            if not ok:
                print(
                    f"warning: {duration:g}s is outside the campaign's duration "
                    f"bound ({bound:g}s) - the compliance gate will refuse this clip",
                    file=sys.stderr,
                )
    candidate = ClipCandidate(start=args.start, end=args.end, score=0.0)
    out = pipeline.render_candidate(
        args.video,
        candidate,
        facecam,
        args.output,
        cfg,
        with_captions=not args.no_captions,
        credit_text=credit,
    )
    print(out)
    return 0


def _cmd_repurpose(args: argparse.Namespace, cfg: config.Config) -> int:
    from . import pipeline

    caption = args.caption or ""
    if args.campaign:
        from .campaigns.store import CampaignStore
        from .campaigns.template import build_caption, template_for

        with CampaignStore(cfg.campaigns.campaigns_db) as store:
            campaign_rec = store.get(args.campaign)
        if campaign_rec is None:
            print(f"unknown campaign: {args.campaign}", file=sys.stderr)
            return 1
        caption = build_caption(caption, template_for(campaign_rec))

    if args.snap and (args.start is not None or args.end is not None):
        from .edit.ffmpeg import probe

        try:
            transcript = pipeline.source_transcript(args.video, cfg)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 2
        except Exception as e:  # model download / network failures
            print(
                f"--snap failed to transcribe ({type(e).__name__}: {str(e)[:120]}). "
                "The Whisper model downloads on first use - check network, or "
                "rerun without --snap.",
                file=sys.stderr,
            )
            return 2
        start0 = args.start if args.start is not None else 0.0
        end0 = args.end if args.end is not None else probe(args.video).duration
        snapped = pipeline.snap_to_speech(transcript, start0, end0)
        if snapped != (start0, end0):
            print(
                f"snapped window {start0:g}-{end0:g}s -> "
                f"{snapped[0]:g}-{snapped[1]:g}s (sentence boundaries)",
                file=sys.stderr,
            )
        args.start, args.end = snapped

    out = pipeline.repurpose_asset(
        args.video,
        args.output,
        cfg,
        hook=args.hook,
        cta=args.cta,
        credit_text=args.credit,
        start=args.start,
        end=args.end,
        with_captions=not args.no_captions,
        style=args.style,
    )
    print(out)
    if caption:
        print(f"caption: {caption}")
    if args.campaign:
        ok = _campaign_gate(
            out, args.campaign, caption, args.platform or "", cfg,
            source=args.source or "",
            credit=" ".join(part for part in (args.credit, args.cta, args.hook) if part),
        )
        print("gate: PASS - ready to post" if ok else "gate: FAIL - fix before posting")
        return 0 if ok else 1
    return 0


def _cmd_fonts(args: argparse.Namespace, cfg: config.Config) -> int:
    from .edit import textcard

    if args.fonts_action == "install":
        for name, status in textcard.install_fonts():
            print(f"  {status:<10} {name}")
        print(f"fonts dir: {textcard.FONT_DIR}")
    else:  # list
        for preset, resolved in textcard.preset_status():
            print(f"  {preset:<14} {resolved}")
    return 0


def _cmd_facecam(args: argparse.Namespace, cfg: config.Config) -> int:
    from .edit.facecam import detect_facecam

    found = detect_facecam(args.video, n_frames=args.frames)
    if found is None:
        print("no facecam detected", file=sys.stderr)
        return 1
    r = found.region
    print(f"{r.x},{r.y},{r.w},{r.h}  score={found.score:.2f}")
    return 0


def _require_permission(streamer: str, cfg: config.Config) -> None:
    from .roster import Roster

    with Roster(cfg.roster_db) as roster:
        entry = roster.require(streamer)
    if entry.exclusions:
        print(f"note - exclusions for {streamer}: {entry.exclusions}", file=sys.stderr)


def _cmd_vod(args: argparse.Namespace, cfg: config.Config) -> int:
    from .ingest.vod import download_vod

    _require_permission(args.streamer, cfg)
    out = download_vod(
        args.vod_id,
        args.output,
        max_height=args.max_height,
        start=args.start,
        end=args.end,
        cookies_file=args.cookies,
    )
    print(out)
    return 0


def _cmd_chat(args: argparse.Namespace, cfg: config.Config) -> int:
    from .ingest.chat_replay import download_chat

    _require_permission(args.streamer, cfg)
    count = download_chat(args.vod_id, args.output)
    print(f"{count} messages -> {args.output}")
    return 0


def _cmd_game_events(args: argparse.Namespace, cfg: config.Config) -> int:
    from .detect.gamecv import detect_events
    from .edit.ffmpeg import probe

    duration = probe(args.video).duration
    series, hits = detect_events(args.video, args.profile, duration, fps=args.fps)
    if not hits:
        print("no events detected")
    for h in hits:
        print(f"{h.at:8.1f}s  {h.name:<20} score={h.score:.2f}")
    return 0


def _cmd_live(args: argparse.Namespace, cfg: config.Config) -> int:
    from .live.irc import chat_messages
    from .live.monitor import default_capture, run_live

    capture = None
    if not args.dry_run:
        capture = default_capture(cfg, args.streamer, args.output_dir)

    def on_event(event) -> None:
        if event.error:
            print(f"spike z={event.z:.1f} - capture FAILED: {event.error}", file=sys.stderr)
        elif event.clip_path:
            print(f"spike z={event.z:.1f} rate={event.rate:.1f}/s -> {event.clip_path}")
        else:
            print(f"spike z={event.z:.1f} rate={event.rate:.1f}/s (dry run)")

    mode = "dry run - detecting only" if args.dry_run else "capturing clips"
    print(f"monitoring #{args.streamer} live chat ({mode}; ctrl-c to stop)", file=sys.stderr)
    try:
        events = run_live(
            args.streamer, cfg, chat_messages(args.streamer), args.output_dir,
            capture=capture, on_event=on_event, max_events=args.max_clips,
        )
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
        return 0
    captured = sum(1 for e in events if e.clip_path)
    print(f"{len(events)} spikes, {captured} clips -> {args.output_dir}/live_events.jsonl")
    return 0


def _cmd_suggest(args: argparse.Namespace, cfg: config.Config) -> int:
    import json
    import os

    from .detect import transcribe
    from .detect.audio import extract_wav
    from .package import hooks

    if not hooks.available():
        print("ANTHROPIC_API_KEY not set - hook generation unavailable", file=sys.stderr)
        return 1
    os.makedirs(cfg.work_dir, exist_ok=True)
    wav = extract_wav(args.video, os.path.join(cfg.work_dir, "suggest.wav"))
    transcript = transcribe.transcribe(wav)
    text = " ".join(s.text.strip() for s in transcript.segments)
    suggestion = hooks.generate(text, args.streamer, model=cfg.llm.model)
    if suggestion is None:
        print("no suggestion generated (empty transcript or declined)", file=sys.stderr)
        return 1
    print(json.dumps(
        {"hook": suggestion.hook, "title": suggestion.title, "hashtags": suggestion.hashtags},
        indent=1,
    ))
    return 0


def _cmd_music_check(args: argparse.Namespace, cfg: config.Config) -> int:
    import os

    from .detect.audio import extract_wav
    from .package.music import check, mute_segments

    os.makedirs(cfg.work_dir, exist_ok=True)
    wav = extract_wav(args.video, os.path.join(cfg.work_dir, "music_check.wav"))
    segments = check(wav, threshold=args.threshold)
    if not segments:
        print("no music-likely segments found")
        return 0
    for s in segments:
        print(f"music-likely: {s.start:7.1f} - {s.end:7.1f}s  score={s.score:.2f}")
    if args.mute:
        out = mute_segments(args.video, args.mute, segments)
        print(f"muted -> {out}")
    return 0


def _screen_for_music(video: str, cfg: config.Config) -> bool:
    """DMCA gate before publishing. Returns True if the clip is clean."""
    import os

    from .detect.audio import extract_wav
    from .package.music import check

    os.makedirs(cfg.work_dir, exist_ok=True)
    wav = extract_wav(video, os.path.join(cfg.work_dir, "publish_check.wav"))
    segments = check(wav)
    for s in segments:
        print(
            f"music-likely: {s.start:.1f}-{s.end:.1f}s score={s.score:.2f}", file=sys.stderr
        )
    return not segments


def _warn_short_for_rewards(video: str) -> None:
    from .edit.ffmpeg import probe

    duration = probe(video).duration
    if duration < 61.0:
        print(
            f"warning: clip is {duration:.0f}s - TikTok Creator Rewards pays only on "
            "videos over 1 minute",
            file=sys.stderr,
        )


def _cmd_auth(args: argparse.Namespace, cfg: config.Config) -> int:
    if args.platform == "youtube":
        from .publish.youtube import YouTubeClient, build_auth_url

        if not args.code:
            print(build_auth_url(cfg.youtube.client_id, cfg.youtube.redirect_uri))
            print(
                "\nOpen the URL, approve, then re-run with --code <code from redirect>",
                file=sys.stderr,
            )
            return 0
        client = YouTubeClient(
            cfg.youtube.client_id, cfg.youtube.client_secret, cfg.youtube.token_file
        )
        client.exchange_code(args.code, cfg.youtube.redirect_uri)
        print(f"tokens saved -> {cfg.youtube.token_file}")
    else:
        from .publish.tiktok import TikTokClient, build_auth_url

        if not args.code:
            print(build_auth_url(cfg.tiktok.client_key, cfg.tiktok.redirect_uri))
            print(
                "\nOpen the URL, approve, then re-run with --code <code from redirect>",
                file=sys.stderr,
            )
            return 0
        client = TikTokClient(
            cfg.tiktok.client_key, cfg.tiktok.client_secret, cfg.tiktok.token_file
        )
        client.exchange_code(args.code, cfg.tiktok.redirect_uri)
        print(f"tokens saved -> {cfg.tiktok.token_file}")
    return 0


def _campaign_gate(
    video: str,
    campaign_id: str,
    caption: str,
    platform: str,
    cfg: config.Config,
    source: str = "",
    credit: str = "",
) -> bool:
    """Compliance pre-flight against a stored campaign. True = clip may export."""
    from .campaigns.gate import ClipFacts, preflight
    from .campaigns.rules import parse_rules
    from .campaigns.store import CampaignStore
    from .edit.ffmpeg import probe

    with CampaignStore(cfg.campaigns.campaigns_db) as store:
        campaign = store.get(campaign_id)
    if campaign is None:
        print(f"unknown campaign: {campaign_id}", file=sys.stderr)
        return False
    report = preflight(
        ClipFacts(
            duration_s=probe(video).duration,
            caption=caption,
            credit_text=credit,
            platform=platform,
            source_url=source,
        ),
        parse_rules(campaign.rules_text),
        campaign,
    )
    for r in report.results:
        stream = sys.stderr if r.status != "pass" else sys.stdout
        print(f"  {r.status:<6} [{r.name}] {r.detail}", file=stream)
    return report.passed


def _cmd_publish(args: argparse.Namespace, cfg: config.Config) -> int:
    if args.campaign:
        caption = " ".join(
            part for part in (args.title, args.description or "", args.tags or "") if part
        )
        if not _campaign_gate(
            args.video, args.campaign, caption, args.platform, cfg,
            source=args.source or "",
        ):
            print(
                "publish refused: campaign compliance gate failed - every rejected "
                "clip is unpaid work. Fix the caption/clip or pick another campaign.",
                file=sys.stderr,
            )
            return 3
    if not args.skip_music_check and not _screen_for_music(args.video, cfg):
        print(
            "publish refused: music-likely segments found. Mute them first "
            "(clipengine music-check --mute) or pass --skip-music-check to override.",
            file=sys.stderr,
        )
        return 3
    if args.platform == "youtube":
        from .publish.youtube import UploadRequest, YouTubeClient

        client = YouTubeClient(
            cfg.youtube.client_id, cfg.youtube.client_secret, cfg.youtube.token_file
        )
        title = args.title if "#shorts" in args.title.lower() else args.title + " #Shorts"
        video_id = client.upload(
            UploadRequest(
                video_path=args.video,
                title=title,
                description=args.description or "",
                tags=args.tags.split(",") if args.tags else [],
                privacy=args.privacy or "private",
            )
        )
        print(f"https://www.youtube.com/shorts/{video_id}")
    else:
        from .publish.tiktok import PostRequest, TikTokClient

        _warn_short_for_rewards(args.video)
        client = TikTokClient(
            cfg.tiktok.client_key, cfg.tiktok.client_secret, cfg.tiktok.token_file
        )
        publish_id = client.post(
            PostRequest(
                video_path=args.video,
                caption=args.title,
                privacy_level=args.privacy or cfg.tiktok.privacy_level,
            )
        )
        print(f"published: {publish_id}")
    return 0


def _rules(cfg: config.Config):
    from .publish.scheduler import ScheduleRules

    return ScheduleRules(
        windows=cfg.schedule.windows,
        min_spacing_hours=cfg.schedule.min_spacing_hours,
        daily_cap=cfg.schedule.daily_cap,
        tz=cfg.schedule.tz,
    )


def _cmd_queue(args: argparse.Namespace, cfg: config.Config) -> int:
    from .publish.scheduler import Queue, run_due

    with Queue(cfg.schedule.queue_db) as queue:
        if args.queue_action == "add":
            if args.campaign:
                caption = " ".join(
                    part for part in (args.title, args.description or "", args.tags or "")
                    if part
                )
                if not _campaign_gate(
                    args.video, args.campaign, caption, args.platform, cfg,
                    source=args.source or "",
                ):
                    print(
                        "queue refused: campaign compliance gate failed",
                        file=sys.stderr,
                    )
                    return 3
            post = queue.add(
                args.platform,
                args.account,
                args.video,
                args.title,
                _rules(cfg),
                description=args.description or "",
                tags=args.tags or "",
                privacy=args.privacy or "",
            )
            print(f"#{post.id} scheduled {post.scheduled_at} [{post.platform}/{post.account}]")
        elif args.queue_action == "list":
            posts = queue.list(status=args.status)
            if not posts:
                print("queue is empty")
            for p in posts:
                marker = {"scheduled": " ", "published": "+", "failed": "!", "cancelled": "x"}
                print(
                    f"{marker.get(p.status, '?')} #{p.id:<4} {p.scheduled_at}  "
                    f"{p.platform}/{p.account}  {p.status:<9} {p.title[:40]}"
                )
        elif args.queue_action == "cancel":
            post = queue.cancel(args.id)
            print(f"#{post.id} cancelled")
        else:  # run
            def screen(video_path: str) -> bool:
                return _screen_for_music(video_path, cfg)

            def publish_youtube(post) -> str:
                from .publish.youtube import UploadRequest, YouTubeClient

                client = YouTubeClient(
                    cfg.youtube.client_id, cfg.youtube.client_secret, cfg.youtube.token_file
                )
                title = post.title if "#shorts" in post.title.lower() else post.title + " #Shorts"
                return client.upload(
                    UploadRequest(
                        video_path=post.video_path,
                        title=title,
                        description=post.description,
                        tags=post.tags.split(",") if post.tags else [],
                        privacy=post.privacy or "private",
                    )
                )

            def publish_tiktok(post) -> str:
                from .publish.tiktok import PostRequest, TikTokClient

                client = TikTokClient(
                    cfg.tiktok.client_key, cfg.tiktok.client_secret, cfg.tiktok.token_file
                )
                return client.post(
                    PostRequest(
                        video_path=post.video_path,
                        caption=post.title,
                        privacy_level=post.privacy or cfg.tiktok.privacy_level,
                    )
                )

            due = queue.due()
            if not due:
                print("nothing due")
                return 0
            if args.dry_run:
                for p in due:
                    print(f"would publish #{p.id} {p.platform}/{p.account}: {p.title}")
                return 0
            results = run_due(
                queue,
                {"youtube": publish_youtube, "tiktok": publish_tiktok},
                screen,
            )
            for post, external_id in results:
                if external_id:
                    print(f"published #{post.id} -> {external_id}")
                else:
                    print(
                        f"attempt failed #{post.id} ({post.status}, "
                        f"attempt {post.attempts}): {post.last_error}",
                        file=sys.stderr,
                    )
    return 0


def _cmd_process(args: argparse.Namespace, cfg: config.Config) -> int:
    from . import pipeline
    from .models import FacecamRegion

    facecam = None
    if args.facecam:
        x, y, w, h = (int(v) for v in args.facecam.split(","))
        facecam = FacecamRegion(x, y, w, h)

    campaign = None
    if args.campaign:
        from .campaigns.store import CampaignStore

        with CampaignStore(cfg.campaigns.campaigns_db) as store:
            campaign = store.get(args.campaign)
        if campaign is None:
            print(f"unknown campaign: {args.campaign}", file=sys.stderr)
            return 1
        if not campaign.open:
            print(
                f"warning: campaign is {campaign.status} - clips may not pay",
                file=sys.stderr,
            )

    manifest = pipeline.process_vod(
        args.video,
        args.chat,
        args.streamer,
        args.output_dir,
        cfg,
        top_n=args.top,
        with_captions=not args.no_captions,
        facecam=facecam,
        campaign=campaign,
    )
    rendered = [m for m in manifest if m["status"] == "rendered"]
    for m in manifest:
        if m["status"] == "rendered":
            mute_note = (
                f"  (muted {len(m['muted_segments'])} music segment(s))"
                if m.get("muted_segments")
                else ""
            )
            gate_note = ""
            if "gate" in m:
                gate_note = (
                    "  gate: PASS" if m["gate"]["passed"]
                    else "  gate: FAIL (" + "; ".join(m["gate"]["failures"]) + ")"
                )
            print(f"#{m['index']} {m['start']:8.1f}-{m['end']:8.1f}s "
                  f"score={m['score']:.2f}  {m['path']}{mute_note}{gate_note}")
        else:
            print(f"#{m['index']} {m['start']:8.1f}-{m['end']:8.1f}s FAILED: {m['error']}",
                  file=sys.stderr)
    print(f"\n{len(rendered)}/{len(manifest)} rendered -> {args.output_dir}/manifest.json")

    if args.queue_platform and rendered:
        from .publish.scheduler import Queue

        if not args.account:
            print("--account is required with --queue-platform", file=sys.stderr)
            return 1
        with Queue(cfg.schedule.queue_db) as queue:
            for m in rendered:
                if m.get("gate") and not m["gate"]["passed"]:
                    print(
                        f"not queued #{m['index']}: campaign gate failed "
                        f"({'; '.join(m['gate']['failures'])})",
                        file=sys.stderr,
                    )
                    continue
                title = m.get("caption") or m.get("suggested_title") or (
                    args.title_template.format(
                        streamer=m["streamer"], i=m["index"], start=int(m["start"])
                    )
                )
                post = queue.add(
                    args.queue_platform, args.account, m["path"], title, _rules(cfg)
                )
                print(f"queued #{post.id} {post.scheduled_at}  {title}")
    return 0


def _cmd_review(args: argparse.Namespace, cfg: config.Config) -> int:
    from .review import ReviewQueue

    with ReviewQueue(cfg.review_db) as rq:
        if args.review_action == "import":
            added, skipped = rq.import_manifest(args.manifest)
            print(f"{added} clips pending review ({skipped} skipped)")
        elif args.review_action == "list":
            clips = rq.list(status=args.status)
            if not clips:
                print("nothing to review" if args.status in (None, "pending") else "no clips")
            for c in clips:
                mark = {"pending": "?", "approved": "+", "rejected": "-"}[c.status]
                extra = c.title or c.reason or ""
                print(
                    f"{mark} #{c.id:<4} {c.streamer:<18} {c.start:7.1f}-{c.end:7.1f}s "
                    f"score={c.score:5.2f}  {c.status:<9} {extra[:40]}  {c.clip_path}"
                )
        elif args.review_action == "approve":
            queued_post_id = None
            if args.queue_platform:
                if not args.account:
                    print("--account is required with --queue-platform", file=sys.stderr)
                    return 1
                from .publish.scheduler import Queue

                clip = rq.get(args.id)
                if clip is None:
                    print(f"no clip {args.id}", file=sys.stderr)
                    return 1
                with Queue(cfg.schedule.queue_db) as queue:
                    post = queue.add(
                        args.queue_platform, args.account, clip.clip_path,
                        args.title, _rules(cfg), privacy=args.privacy or "",
                    )
                queued_post_id = post.id
            clip = rq.approve(args.id, args.title, queued_post_id=queued_post_id)
            queued = f", queued as post #{queued_post_id}" if queued_post_id else ""
            print(f"#{clip.id} approved: {clip.title}{queued}")
        elif args.review_action == "reject":
            clip = rq.reject(args.id, args.reason)
            print(f"#{clip.id} rejected: {clip.reason}")
        else:  # stats
            s = rq.stats()
            rate = f"{s['pass_rate']:.0%}" if s["pass_rate"] is not None else "n/a"
            target = ""
            if s["pass_rate"] is not None:
                target = "  (MVP target >=50%: " + (
                    "MET" if s["pass_rate"] >= 0.5 else "NOT met"
                ) + ")"
            print(
                f"pending={s['pending']} approved={s['approved']} "
                f"rejected={s['rejected']}  pass rate: {rate}{target}"
            )
            for reason, count in s["rejection_reasons"].items():
                print(f"  rejection x{count}: {reason}")
    return 0


def _cmd_truth(args: argparse.Namespace, cfg: config.Config) -> int:
    import json

    from .ingest.twitch import TwitchClient

    client = TwitchClient(cfg.twitch)
    clips = client.vod_clips(args.streamer, args.vod_id)
    if not clips:
        print("no viewer clips with vod offsets found for this VOD", file=sys.stderr)
        return 1
    with open(args.output, "w") as f:
        json.dump(clips, f, indent=1)
    print(f"{len(clips)} viewer-clipped moments -> {args.output}")
    return 0


def _cmd_tune(args: argparse.Namespace, cfg: config.Config) -> int:
    import json

    from . import pipeline
    from .detect.tune import to_config_toml, tune

    with open(args.truth) as f:
        truth = json.load(f)
    series, _, duration = pipeline.compute_series(args.video, args.chat, cfg)
    results = tune(
        series, duration, truth, cfg.detect, top_n=args.top_n, top_truth=args.top_truth
    )
    print(f"evaluated {len(results)} weight configs against {min(args.top_truth, len(truth))} "
          f"truth moments (recall@{args.top_n or cfg.detect.top_n})\n")
    for weights, ev in results[:10]:
        w = "  ".join(f"{k.replace('weight_', '')}={v:g}" for k, v in sorted(weights.items()))
        print(f"recall={ev.recall:.2f} hits={ev.hits}/{ev.n_truth} "
              f"mean_rank={ev.mean_hit_rank:.1f}   {w}")
    best_weights, best_eval = results[0]
    if args.write_config:
        with open(args.write_config, "w") as f:
            f.write(to_config_toml(best_weights))
        print(f"\nbest config -> {args.write_config}")
    return 0


def _cmd_stats(args: argparse.Namespace, cfg: config.Config) -> int:
    from . import analytics
    from .publish.scheduler import Queue

    with Queue(cfg.schedule.queue_db) as queue, analytics.StatsStore(
        cfg.analytics.stats_db
    ) as store:
        if args.stats_action == "sync":
            fetchers = {}
            if cfg.youtube.client_id:
                from .publish.youtube import YouTubeClient

                yt = YouTubeClient(
                    cfg.youtube.client_id, cfg.youtube.client_secret, cfg.youtube.token_file
                )
                fetchers["youtube"] = yt.stats
            if cfg.tiktok.client_key:
                from .publish.tiktok import TikTokClient

                tt = TikTokClient(
                    cfg.tiktok.client_key, cfg.tiktok.client_secret, cfg.tiktok.token_file
                )
                fetchers["tiktok"] = tt.video_stats
            if not fetchers:
                print("no platform credentials configured - nothing to sync", file=sys.stderr)
                return 1
            count = analytics.sync(queue, store, fetchers)
            print(f"{count} snapshots recorded")
        else:  # report
            rows = analytics.report(queue, store)
            if not rows:
                print("no published posts yet")
                return 0
            for r in rows:
                print(
                    f"{r.views:>9}v {r.likes:>7}l  {r.platform}/{r.account}  "
                    f"#{r.post_id} {r.title[:44]}"
                )
            print()
            for (platform, account), t in analytics.account_totals(rows).items():
                print(
                    f"{platform}/{account}: {t['posts']} posts, "
                    f"{t['views']} views, {t['likes']} likes"
                )
            if args.csv:
                analytics.write_csv(rows, args.csv)
                print(f"\ncsv -> {args.csv}")
    return 0


def _cmd_roster(args: argparse.Namespace, cfg: config.Config) -> int:
    from .roster import PermissionError_, Roster

    with Roster(cfg.roster_db) as roster:
        if args.roster_action == "add":
            entry = roster.add(
                args.streamer,
                source=args.source,
                evidence=args.evidence,
                credit=args.credit or "",
                exclusions=args.exclusions or "",
                notes=args.notes or "",
            )
            print(f"allowed: {entry.login} ({entry.source}, granted {entry.granted_at})")
        elif args.roster_action == "import":
            imported, errors = roster.import_csv(args.csv, default_source=args.source)
            for line in errors:
                print(f"skipped {line}", file=sys.stderr)
            allowed_total = len(roster.list(status="allowed"))
            print(
                f"{len(imported)} imported, {len(errors)} skipped - "
                f"roster now has {allowed_total} allowed streamer(s)"
            )
            if errors:
                return 1
        elif args.roster_action == "export":
            count = roster.export_csv(args.output)
            print(f"{count} entries -> {args.output}")
        elif args.roster_action == "revoke":
            entry = roster.revoke(args.streamer, reason=args.reason or "")
            print(f"revoked: {entry.login} at {entry.revoked_at}")
        elif args.roster_action == "check":
            try:
                entry = roster.require(args.streamer)
                print(f"allowed: {entry.login} ({entry.source}, evidence: {entry.evidence})")
            except PermissionError_ as e:
                print(str(e), file=sys.stderr)
                return 1
        else:  # list
            entries = roster.list(status=args.status)
            if not entries:
                print("roster is empty")
            for e in entries:
                flag = "+" if e.allowed else "-"
                print(f"{flag} {e.login:<24} {e.source:<17} {e.evidence}")
    return 0


def _print_checklist(check) -> None:
    if check.hashtags:
        print(f"  hashtags: {' '.join('#' + h for h in check.hashtags)}")
    if check.mentions:
        print(f"  mentions: {' '.join('@' + m for m in check.mentions)}")
    if check.min_duration_s is not None or check.max_duration_s is not None:
        lo = f"{check.min_duration_s:g}s" if check.min_duration_s is not None else "-"
        hi = f"{check.max_duration_s:g}s" if check.max_duration_s is not None else "-"
        print(f"  duration: {lo} .. {hi}")
    if check.platforms:
        print(f"  platforms: {', '.join(check.platforms)}")
    for line in check.required:
        print(f"  must: {line}")
    for line in check.banned:
        print(f"  banned: {line}")
    for link in check.links:
        print(f"  source: {link}")
    print(f"  complexity: {check.complexity} (simplicity {check.simplicity:.2f})")


def _cmd_campaigns(args: argparse.Namespace, cfg: config.Config) -> int:
    from .campaigns.models import Campaign
    from .campaigns.rules import parse_rules
    from .campaigns.score import rank, score_campaign
    from .campaigns.store import CampaignStore

    if args.campaigns_action == "rules" and args.file:
        with open(args.file) as f:
            _print_checklist(parse_rules(f.read()))
        return 0
    if args.campaigns_action == "check":
        ok = _campaign_gate(
            args.video, args.campaign, args.caption or "", args.platform or "",
            cfg, source=args.source or "", credit=args.credit or "",
        )
        print("PASS - clip may export" if ok else "FAIL - do not export")
        return 0 if ok else 1

    with CampaignStore(cfg.campaigns.campaigns_db) as store:
        if args.campaigns_action == "discover":
            import httpx as _httpx

            from .campaigns import alerts, discover

            if args.file:
                with open(args.file, encoding="utf-8", errors="replace") as f:
                    page = f.read()
            elif args.browser:
                try:
                    page = discover.render_discover(args.url)
                except RuntimeError as e:
                    print(str(e), file=sys.stderr)
                    return 2
            else:
                try:
                    page = discover.fetch_discover(args.url)
                except _httpx.HTTPError as e:
                    print(
                        f"fetch failed ({e}). Try --browser (renders the page in "
                        "headless Chromium), or save the page from your browser "
                        "and re-run with --file page.html",
                        file=sys.stderr,
                    )
                    return 2
            if args.dump:
                with open(args.dump, "w", encoding="utf-8") as f:
                    f.write(page)
                print(f"page saved -> {args.dump}", file=sys.stderr)
            if args.debug:
                contexts = discover.card_contexts(page)
                for n, ctx in enumerate(contexts[:6], start=1):
                    print(f"----- card {n} context -----")
                    for ln in ctx:
                        print(f"  {ln[:110]}")
                print(f"({len(contexts)} rate lines total)")
                return 0
            found = discover.parse_discover(page)
            if not found:
                print(
                    "no campaign cards parsed. The feed is client-rendered, so a "
                    "plain fetch sees no cards - try --browser (pip install "
                    "'clipengine[browser]' && playwright install chromium). "
                    "Page diagnostics:\n" + discover.diagnose(page),
                    file=sys.stderr,
                )
                return 1
            plausible = [d for d in found if d.rate <= args.max_cpm]
            suspect = len(found) - len(plausible)
            if suspect:
                print(
                    f"({suspect} dropped: rate above --max-cpm {args.max_cpm:g}/1k - "
                    "real CPMs run ~$0.50-$15; higher usually means a mis-parsed "
                    "card, verify on the page)",
                    file=sys.stderr,
                )
            candidates = [d.to_campaign() for d in plausible
                          if d.rate >= (args.min_cpm or 0.0)]
            scored = rank(candidates, cfg.campaigns.familiarity)
            if args.sort == "rate":
                scored.sort(key=lambda s: s.campaign.reward_amount, reverse=True)
            elif args.sort == "budget":
                scored.sort(key=lambda s: s.campaign.budget_remaining, reverse=True)
            shown = scored[: args.top] if args.top else scored
            for s in shown:
                c = s.campaign
                plats = ",".join(c.platforms) or "-"
                print(
                    f"[{s.score:6.1f}] {c.reward_amount:>5g}/1k  "
                    f"{c.budget_remaining:>10g} left  {plats:<28} {c.title[:44]}"
                )
            dropped = len(plausible) - len(candidates)
            if dropped:
                print(f"({dropped} below --min-cpm {args.min_cpm:g})", file=sys.stderr)
            if args.add:
                new = store.upsert([s.campaign for s in shown])
                print(f"stored {len(shown)} campaign(s), {len(new)} new")
                alertable = [
                    s for s in rank(new, cfg.campaigns.familiarity)
                    if s.score >= cfg.campaigns.alert_min_score
                ]
                if alertable and cfg.campaigns.alert_webhook:
                    ok = alerts.notify(cfg.campaigns.alert_webhook, alertable)
                    print(f"alert {'sent' if ok else 'FAILED'} ({len(alertable)})")
                print(
                    "note: rules text is not on the discover feed - open each "
                    "campaign page and attach its brief before producing: "
                    "clipengine campaigns rules disc:ID --attach brief.txt",
                )
            return 0
        if args.campaigns_action == "sync":
            from .campaigns import alerts
            from .campaigns.whop import WhopClient, WhopError

            try:
                client = WhopClient(cfg.campaigns.api_key)
            except WhopError as e:
                print(str(e), file=sys.stderr)
                return 2
            fetched: list[Campaign] = []
            try:
                for status in cfg.campaigns.statuses:
                    fetched.extend(
                        client.campaigns(
                            status=status,
                            goal_types=tuple(cfg.campaigns.goal_types) or None,
                            with_rules=not args.no_rules,
                        )
                    )
            except WhopError as e:
                print(str(e), file=sys.stderr)
                return 2
            new = store.upsert(fetched)
            print(f"synced {len(fetched)} campaign(s), {len(new)} new")
            alertable = [
                s for s in rank(new, cfg.campaigns.familiarity)
                if s.score >= cfg.campaigns.alert_min_score
            ]
            for s in alertable:
                print(f"  new: [{s.score:.1f}] {s.campaign.title} ({s.campaign.id})")
            if alertable and cfg.campaigns.alert_webhook:
                ok = alerts.notify(cfg.campaigns.alert_webhook, alertable)
                print(f"alert {'sent' if ok else 'FAILED'} ({len(alertable)} campaign(s))")
        elif args.campaigns_action == "add":
            slug = args.id or "manual:" + "-".join(args.title.lower().split())[:48]
            rules_text = args.rules or ""
            if args.rules_file:
                with open(args.rules_file) as f:
                    rules_text = f.read()
            campaign = Campaign(
                id=slug,
                source="manual",
                title=args.title,
                brand=args.brand or "",
                goal_type=args.goal,
                status="open",
                currency=args.currency,
                reward_model="cpm",
                reward_amount=args.cpm,
                budget_total=args.budget,
                budget_remaining=args.remaining if args.remaining is not None else args.budget,
                platforms=[p.strip() for p in (args.platforms or "").split(",") if p.strip()],
                rules_text=rules_text,
                url=args.url or "",
            )
            store.upsert([campaign])
            scored = score_campaign(campaign, cfg.campaigns.familiarity)
            print(f"added {campaign.id} [score {scored.score:.1f}]")
        elif args.campaigns_action == "list":
            scored = rank(store.list(status=args.status), cfg.campaigns.familiarity)
            if not scored:
                print("no campaigns - run 'campaigns sync' or 'campaigns add'")
            for s in scored[: args.top] if args.top else scored:
                c = s.campaign
                reward = (
                    f"{c.reward_amount:g}/1k"
                    if c.reward_model == "cpm"
                    else f"{c.reward_amount:g}/sub"
                )
                print(
                    f"[{s.score:6.1f}] {c.id:<28} {c.status:<9} {reward:>9}  "
                    f"{c.budget_remaining:>9g} left  {c.title[:40]}"
                )
        elif args.campaigns_action == "show":
            c = store.get(args.id)
            if c is None:
                print(f"unknown campaign: {args.id}", file=sys.stderr)
                return 1
            s = score_campaign(c, cfg.campaigns.familiarity)
            reward_unit = "per 1k views" if c.reward_model == "cpm" else "per submission"
            print(f"{c.title} ({c.id}, {c.source})")
            print(f"  brand: {c.brand or '-'}  goal: {c.goal_type or '-'}  status: {c.status}")
            print(f"  reward: {c.reward_amount:g} {c.currency} {reward_unit}")
            print(
                f"  budget: {c.budget_remaining:g}/{c.budget_total:g} {c.currency} remaining"
                + (f", {c.spots_remaining} spot(s)" if c.spots_remaining is not None else "")
            )
            print(f"  score: {s.score:.2f}  {s.breakdown}")
            if c.rules_text:
                print("  rules checklist:")
                _print_checklist(s.checklist)
            history = store.history(c.id)
            if len(history) > 1:
                print("  budget history:")
                for snap in history[-args.snapshots:]:
                    print(f"    {snap.at}  {snap.budget_remaining:g} remaining ({snap.status})")
        else:  # rules for a stored campaign
            if not args.id:
                print("give a campaign id or --file", file=sys.stderr)
                return 1
            c = store.get(args.id)
            if c is None:
                print(f"unknown campaign: {args.id}", file=sys.stderr)
                return 1
            if args.attach:
                with open(args.attach) as f:
                    c.rules_text = f.read()
                store.upsert([c])
                print(f"rules attached to {c.id}:")
            elif not c.rules_text:
                print("no rules text stored - attach the campaign brief with "
                      "'campaigns rules ID --attach brief.txt'")
                return 1
            _print_checklist(parse_rules(c.rules_text))
    return 0


def _cmd_submissions(args: argparse.Namespace, cfg: config.Config) -> int:
    from .campaigns.store import CampaignStore
    from .campaigns.submissions import (
        REJECTION_RATE_TARGET,
        SubmissionStore,
    )

    def show(sub) -> None:
        marker = {"pending": "?", "approved": "+", "rejected": "x", "paid": "$"}
        extra = ""
        if sub.status == "paid":
            extra = f"  {sub.amount:g} paid"
        elif sub.status == "rejected":
            extra = f"  ({sub.rejection_reason})"
        print(
            f"{marker[sub.status]} #{sub.id:<4} {sub.status:<9} {sub.campaign_id:<28} "
            f"{sub.views:>8} views{extra}  {sub.post_url}"
        )

    with SubmissionStore(cfg.campaigns.campaigns_db) as subs:
        if args.submissions_action == "add":
            with CampaignStore(cfg.campaigns.campaigns_db) as store:
                campaign = store.get(args.campaign)
            if campaign is None:
                print(f"unknown campaign: {args.campaign}", file=sys.stderr)
                return 1
            if not campaign.open:
                print(
                    f"warning: campaign is {campaign.status} - submissions may not pay",
                    file=sys.stderr,
                )
            sub = subs.add(
                args.campaign, args.url,
                platform=args.platform or "", account=args.account or "",
                title=args.title or "",
            )
            print(f"#{sub.id} pending: {sub.post_url} -> {sub.campaign_id}")
        elif args.submissions_action == "list":
            entries = subs.list(status=args.status, campaign_id=args.campaign)
            if not entries:
                print("no submissions tracked")
            for sub in entries:
                show(sub)
        elif args.submissions_action == "approve":
            show(subs.approve(args.id))
        elif args.submissions_action == "reject":
            show(subs.reject(args.id, args.reason))
        elif args.submissions_action == "paid":
            if args.views is not None:
                subs.set_views(args.id, args.views)
            show(subs.mark_paid(args.id, args.amount))
        elif args.submissions_action == "views":
            show(subs.set_views(args.id, args.views))
        elif args.submissions_action == "sync":
            moved = subs.auto_approve()
            if not moved:
                print("nothing past the 48h auto-approval window")
            for sub in moved:
                print(f"#{sub.id} auto-approved (submitted {sub.submitted_at})")
                print(
                    "  verify on Whop - auto-approval assumes the brand didn't reject",
                    file=sys.stderr,
                )
        elif args.submissions_action == "stats":
            with CampaignStore(cfg.campaigns.campaigns_db) as store:
                campaigns = {c.id: c for c in store.list()}
            rollup = subs.earnings(campaigns)
            if not rollup:
                print("no submissions tracked")
                return 0
            grand_paid = grand_views = 0.0
            for e in rollup:
                rate = e.rejection_rate
                rate_s = f"{rate:.0%}" if rate is not None else "n/a"
                flag = (
                    "  <-- over 15% target"
                    if rate is not None and rate > REJECTION_RATE_TARGET
                    else ""
                )
                cpm = e.effective_cpm
                cpm_s = f"{cpm:.2f}/1k" if cpm is not None else "-"
                tta = (
                    f"{e.avg_hours_to_approval:.0f}h"
                    if e.avg_hours_to_approval is not None
                    else "-"
                )
                title = campaigns.get(e.campaign_id)
                print(f"{e.campaign_id}  ({title.title if title else 'unknown campaign'})")
                print(
                    f"  {e.total} submitted: {e.pending} pending, {e.approved} approved, "
                    f"{e.paid} paid, {e.rejected} rejected (rate {rate_s}){flag}"
                )
                print(
                    f"  paid {e.paid_amount:g} (+{e.expected_amount:g} expected), "
                    f"{e.views} views, effective CPM {cpm_s}, approval time {tta}"
                )
                grand_paid += e.paid_amount
                grand_views += e.views
            print(
                f"TOTAL paid {grand_paid:g} across {int(grand_views)} views"
                + (
                    f" (overall CPM {grand_paid / grand_views * 1000:.2f}/1k)"
                    if grand_views and grand_paid
                    else ""
                )
            )
        else:  # reconcile
            from .campaigns.whop import WhopClient, WhopError

            rollup = subs.earnings()
            paid_total = sum(e.paid_amount for e in rollup)
            expected = sum(e.expected_amount for e in rollup)
            print(f"tracker: {paid_total:g} recorded as paid, {expected:g} expected outstanding")
            if not (args.user or args.ledger):
                print("pass --user user_xxx and/or --ledger ldgr_xxx to compare against Whop")
                return 0
            try:
                client = WhopClient(cfg.campaigns.api_key)
                if args.user:
                    payouts = client.payouts(user_id=args.user)
                    completed = sum(
                        float(p.get("amount") or 0)
                        for p in payouts
                        if p.get("status") == "completed"
                    )
                    print(f"whop: {completed:g} withdrawn ({len(payouts)} payout(s))")
                if args.ledger:
                    balance = (client.ledger_account(args.ledger).get("balance") or {})
                    print(
                        f"whop: balance {balance.get('balance', 0):g}, "
                        f"pending {balance.get('pending_balance', 0):g}"
                    )
            except WhopError as e:
                print(str(e), file=sys.stderr)
                return 2
    return 0


def _cmd_vods(args: argparse.Namespace, cfg: config.Config) -> int:
    from .ingest.twitch import TwitchClient

    client = TwitchClient(cfg.twitch)
    for vod in client.recent_vods(args.streamer, limit=args.limit):
        print(f"{vod['id']}  {vod['duration']:>8}  {vod['created_at']}  {vod['title']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clipengine")
    parser.add_argument("--config", help="path to config TOML", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("detect", help="score a VOD and print ranked clip candidates")
    p.add_argument("video")
    p.add_argument("--chat", help="chat log JSONL ({offset, user, text} per line)")
    p.set_defaults(func=_cmd_detect)

    p = sub.add_parser("render", help="cut, reformat 9:16, caption, and render one clip")
    p.add_argument("video")
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--facecam", help="facecam ROI in source px: X,Y,W,H (auto-detected if omitted)")
    p.add_argument("--streamer", help="burn this streamer's roster credit into the clip")
    p.add_argument("--credit", help="explicit credit overlay text (overrides roster)")
    p.add_argument("--no-credit", action="store_true", help="private test renders only")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--campaign",
                   help="apply this campaign's template: mandated credit, duration bounds")
    p.set_defaults(func=_cmd_render)

    p = sub.add_parser(
        "repurpose",
        help="repurpose provided asset footage (UGC/reposting campaigns): "
             "fit-to-9:16 blurred fill, captions, hook, CTA - no facecam",
    )
    p.add_argument("video", help="the campaign-provided asset file")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--hook", help="hook text burned over the first 2.5s")
    p.add_argument("--cta", help="call-to-action drawn into the frame")
    p.add_argument("--credit", help="credit/watermark line at the top")
    p.add_argument("--start", type=float, help="trim start (seconds)")
    p.add_argument("--end", type=float, help="trim end (seconds)")
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--snap", action="store_true",
                   help="snap --start/--end to sentence boundaries via Whisper so the "
                        "clip never opens or closes mid-sentence (needs clipengine[asr]; "
                        "the source transcript is cached beside the file)")
    p.add_argument("--style", default="clean",
                   choices=["clean", "hormozi", "hormozi-green", "beast", "block", "playful"],
                   help="text-card look: font + accent colour preset "
                        "(install fonts once: clipengine fonts install)")
    p.add_argument("--campaign", help="build a compliant caption + run the gate after rendering")
    p.add_argument("--caption", help="caption base text (campaign tokens are appended)")
    p.add_argument("--platform", choices=["tiktok", "youtube", "instagram", "x", "facebook"])
    p.add_argument("--source", help="asset source URL (campaign source check)")
    p.set_defaults(func=_cmd_repurpose)

    p = sub.add_parser("fonts", help="clipper font packs for text cards (free/OFL)")
    fsub = p.add_subparsers(dest="fonts_action", required=True)
    fsub.add_parser("install", help="download the preset fonts to ~/.clipengine/fonts")
    fsub.add_parser("list", help="show each style preset's resolved font")
    p.set_defaults(func=_cmd_fonts)

    p = sub.add_parser("facecam", help="auto-detect the facecam region of a video")
    p.add_argument("video")
    p.add_argument("--frames", type=int, default=24, help="frames to sample")
    p.set_defaults(func=_cmd_facecam)

    p = sub.add_parser("vod", help="download a VOD's video (optionally a time slice)")
    p.add_argument("vod_id", help="VOD id or twitch.tv/videos/... URL")
    p.add_argument("--streamer", required=True, help="streamer login (checked against roster)")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--max-height", type=int, default=1080)
    p.add_argument("--start", type=float, help="slice start (seconds)")
    p.add_argument("--end", type=float, help="slice end (seconds)")
    p.add_argument("--cookies", help="browser cookies file (sub-only VODs)")
    p.set_defaults(func=_cmd_vod)

    p = sub.add_parser("chat", help="download a VOD's chat replay to JSONL")
    p.add_argument("vod_id")
    p.add_argument("--streamer", required=True, help="streamer login (checked against roster)")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=_cmd_chat)

    p = sub.add_parser("auth", help="authorise a publishing account (one-time per account)")
    p.add_argument("platform", choices=["youtube", "tiktok"])
    p.add_argument("--code", help="authorisation code from the consent redirect")
    p.set_defaults(func=_cmd_auth)

    p = sub.add_parser("publish", help="publish a clip (runs the music-DMCA gate first)")
    p.add_argument("platform", choices=["youtube", "tiktok"])
    p.add_argument("video")
    p.add_argument("--title", required=True, help="video title / TikTok caption")
    p.add_argument("--description", help="YouTube description")
    p.add_argument("--tags", help="comma-separated tags (YouTube)")
    p.add_argument("--privacy", help="youtube: private|unlisted|public; tiktok: SELF_ONLY|...")
    p.add_argument("--skip-music-check", action="store_true")
    p.add_argument("--campaign", help="campaign id: run the compliance gate before publishing")
    p.add_argument("--source", help="source URL of the footage (campaign source check)")
    p.set_defaults(func=_cmd_publish)

    p = sub.add_parser("game-events", help="scan a video with a game profile (killfeed/victory CV)")
    p.add_argument("video")
    p.add_argument("--profile", required=True, help="game profile directory")
    p.add_argument("--fps", type=float, default=1.0, help="scan rate (frames/sec)")
    p.set_defaults(func=_cmd_game_events)

    p = sub.add_parser("live", help="monitor a live stream's chat; capture clips on hype spikes")
    p.add_argument("streamer", help="streamer login (must be on the roster)")
    p.add_argument("-o", "--output-dir", required=True)
    p.add_argument("--dry-run", action="store_true", help="detect spikes without creating clips")
    p.add_argument("--max-clips", type=int, help="stop after this many spikes")
    p.set_defaults(func=_cmd_live)

    p = sub.add_parser("suggest", help="LLM hook/title/hashtags for an existing clip")
    p.add_argument("video")
    p.add_argument("--streamer", required=True)
    p.set_defaults(func=_cmd_suggest)

    p = sub.add_parser("music-check", help="screen a clip for music-likely segments (DMCA)")
    p.add_argument("video")
    p.add_argument("--threshold", type=float, default=0.30)
    p.add_argument("--mute", metavar="OUT", help="write a copy with flagged segments muted")
    p.set_defaults(func=_cmd_music_check)

    p = sub.add_parser("queue", help="scheduled publishing queue")
    qsub = p.add_subparsers(dest="queue_action", required=True)
    qa = qsub.add_parser("add", help="queue a clip; a slot is assigned automatically")
    qa.add_argument("platform", choices=["youtube", "tiktok"])
    qa.add_argument("video")
    qa.add_argument("--account", required=True, help="account label (spacing/caps are per account)")
    qa.add_argument("--title", required=True)
    qa.add_argument("--description")
    qa.add_argument("--tags", help="comma-separated (YouTube)")
    qa.add_argument("--privacy")
    qa.add_argument("--campaign", help="campaign id: run the compliance gate before queuing")
    qa.add_argument("--source", help="source URL of the footage (campaign source check)")
    qa.set_defaults(func=_cmd_queue)
    ql = qsub.add_parser("list")
    ql.add_argument("--status", choices=["scheduled", "published", "failed", "cancelled"])
    ql.set_defaults(func=_cmd_queue)
    qc = qsub.add_parser("cancel")
    qc.add_argument("id", type=int)
    qc.set_defaults(func=_cmd_queue)
    qr = qsub.add_parser("run", help="publish everything due (cron this)")
    qr.add_argument("--dry-run", action="store_true")
    qr.set_defaults(func=_cmd_queue)
    p.set_defaults(func=_cmd_queue)

    p = sub.add_parser(
        "process", help="whole-VOD batch: detect -> render top-N credited clips -> music screen"
    )
    p.add_argument("video")
    p.add_argument("--chat", help="chat log JSONL (strongly recommended)")
    p.add_argument("--streamer", required=True, help="roster streamer; credit is burned in")
    p.add_argument("-o", "--output-dir", required=True)
    p.add_argument("--top", type=int, help="clips to render (default: detect.top_n)")
    p.add_argument("--facecam", help="X,Y,W,H override (auto-detected if omitted)")
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--queue-platform", choices=["youtube", "tiktok"],
                   help="also enqueue rendered clips for publishing")
    p.add_argument("--account", help="publish account (required with --queue-platform)")
    p.add_argument("--title-template", default="{streamer} clip {i}",
                   help="queue titles; placeholders: {streamer} {i} {start}")
    p.add_argument("--campaign",
                   help="apply this campaign's render template: duration bounds steer "
                        "detection, mandated credit is burned in, captions carry the "
                        "required tags, and the gate report lands in the manifest")
    p.set_defaults(func=_cmd_process)

    p = sub.add_parser("review", help="human review queue for rendered clips")
    vsub = p.add_subparsers(dest="review_action", required=True)
    vi = vsub.add_parser("import", help="add a process manifest's rendered clips as pending")
    vi.add_argument("manifest")
    vi.set_defaults(func=_cmd_review)
    vl = vsub.add_parser("list")
    vl.add_argument("--status", choices=["pending", "approved", "rejected"])
    vl.set_defaults(func=_cmd_review)
    va = vsub.add_parser("approve")
    va.add_argument("id", type=int)
    va.add_argument("--title", required=True, help="the real publish title")
    va.add_argument("--queue-platform", choices=["youtube", "tiktok"],
                    help="also enqueue for publishing")
    va.add_argument("--account")
    va.add_argument("--privacy")
    va.set_defaults(func=_cmd_review)
    vr = vsub.add_parser("reject")
    vr.add_argument("id", type=int)
    vr.add_argument("--reason", required=True,
                    help="why (feeds tuning), e.g. 'not funny', 'cut too early'")
    vr.set_defaults(func=_cmd_review)
    vs = vsub.add_parser("stats", help="pass rate vs the MVP >=50% criterion")
    vs.set_defaults(func=_cmd_review)

    p = sub.add_parser("truth", help="fetch viewer-clipped moments of a VOD (detector ground truth)")
    p.add_argument("vod_id")
    p.add_argument("--streamer", required=True)
    p.add_argument("-o", "--output", required=True, help="truth JSON path")
    p.set_defaults(func=_cmd_truth)

    p = sub.add_parser("tune", help="grid-search detector weights against truth moments")
    p.add_argument("video")
    p.add_argument("--chat", help="chat log JSONL")
    p.add_argument("--truth", required=True, help="truth JSON from 'clipengine truth'")
    p.add_argument("--top-n", type=int, help="candidate windows considered (default: detect.top_n)")
    p.add_argument("--top-truth", type=int, default=10, help="truth moments considered")
    p.add_argument("--write-config", metavar="TOML", help="write the best weights as config")
    p.set_defaults(func=_cmd_tune)

    p = sub.add_parser("stats", help="performance analytics for published posts")
    ssub = p.add_subparsers(dest="stats_action", required=True)
    ss = ssub.add_parser("sync", help="snapshot current stats for all published posts")
    ss.set_defaults(func=_cmd_stats)
    sr = ssub.add_parser("report", help="latest metrics per post + account totals")
    sr.add_argument("--csv", help="also write the report to this CSV path")
    sr.set_defaults(func=_cmd_stats)

    p = sub.add_parser("roster", help="manage the streamer permission roster")
    rsub = p.add_subparsers(dest="roster_action", required=True)
    ra = rsub.add_parser("add", help="record (or re-grant) a streamer's permission")
    ra.add_argument("streamer")
    ra.add_argument("--source", required=True, choices=["published_policy", "opt_in", "licence"])
    ra.add_argument("--evidence", required=True, help="clip-policy URL or consent reference")
    ra.add_argument("--credit", help="required credit format, e.g. '@name in caption'")
    ra.add_argument("--exclusions", help="content the streamer excluded, e.g. sponsor segments")
    ra.add_argument("--notes")
    ri = rsub.add_parser("import", help="bulk-add streamers from CSV (login,evidence[,source,credit,exclusions,notes])")
    ri.add_argument("csv")
    ri.add_argument("--source", default="published_policy",
                    choices=["published_policy", "opt_in", "licence"],
                    help="default for rows without a source column")
    re_ = rsub.add_parser("export", help="write the whole roster to CSV")
    re_.add_argument("-o", "--output", required=True)
    rr = rsub.add_parser("revoke", help="revoke a streamer's permission (immediate)")
    rr.add_argument("streamer")
    rr.add_argument("--reason")
    rc = rsub.add_parser("check", help="check whether ingestion is allowed")
    rc.add_argument("streamer")
    rl = rsub.add_parser("list")
    rl.add_argument("--status", choices=["allowed", "revoked"])
    p.set_defaults(func=_cmd_roster)

    p = sub.add_parser(
        "campaigns",
        help="Whop campaign intelligence: discover, score, and track paid clipping campaigns",
    )
    csub = p.add_subparsers(dest="campaigns_action", required=True)
    cs = csub.add_parser(
        "sync",
        help="fetch open Workforce Bounties (read-only), store, alert on new high-scorers",
    )
    cs.add_argument("--no-rules", action="store_true",
                    help="skip per-bounty detail fetches (faster; keeps stored rules)")
    ca = csub.add_parser(
        "add", help="manually add a CPM Content Rewards campaign (no public API for these)"
    )
    ca.add_argument("--title", required=True)
    ca.add_argument("--cpm", type=float, required=True, help="reward per 1,000 verified views")
    ca.add_argument("--budget", type=float, required=True, help="total campaign budget")
    ca.add_argument("--remaining", type=float, help="remaining budget (default: total)")
    ca.add_argument("--brand")
    ca.add_argument("--goal", default="clipping", choices=["clipping", "ugc_content"])
    ca.add_argument("--currency", default="usd")
    ca.add_argument("--platforms", help="comma-separated, e.g. tiktok,youtube,instagram")
    ca.add_argument("--rules", help="rules text inline")
    ca.add_argument("--rules-file", help="file containing the campaign rules/brief")
    ca.add_argument("--url", help="campaign page URL")
    ca.add_argument("--id", help="campaign id (default: manual:<title-slug>)")
    cl = csub.add_parser("list", help="stored campaigns ranked by score")
    cl.add_argument("--status", help="filter, e.g. open")
    cl.add_argument("--top", type=int, help="show only the top N")
    cw = csub.add_parser("show", help="one campaign: score breakdown, rules, budget history")
    cw.add_argument("id")
    cw.add_argument("--snapshots", type=int, default=10, help="history rows to show")
    cr = csub.add_parser("rules", help="parsed rules checklist for a campaign or a text file")
    cr.add_argument("id", nargs="?", help="stored campaign id")
    cr.add_argument("--file", help="parse this file instead of a stored campaign")
    cr.add_argument("--attach", help="store this file's text as the campaign's rules")
    cd_ = csub.add_parser(
        "discover",
        help="parse the public Content Rewards discover feed, rank by best rewards "
             "(read-only; the CPM campaigns have no API)",
    )
    cd_.add_argument("--url", default="https://whop.com/discover/app/app_QRxsQodZgK1r4D/")
    cd_.add_argument("--file", help="parse a browser-saved copy of the page instead of fetching")
    cd_.add_argument("--browser", action="store_true",
                     help="render in headless Chromium first (the feed is client-"
                          "rendered; needs clipengine[browser] + playwright install chromium)")
    cd_.add_argument("--dump", help="also save the fetched/rendered page HTML to this file")
    cd_.add_argument("--debug", action="store_true",
                     help="print the raw text lines around each campaign card (parser tuning)")
    cd_.add_argument("--top", type=int, help="show only the top N")
    cd_.add_argument("--min-cpm", type=float, help="drop campaigns paying less per 1k views")
    cd_.add_argument("--max-cpm", type=float, default=25.0,
                     help="plausibility ceiling - rates above this are usually "
                          "mis-parsed cards (default 25)")
    cd_.add_argument("--sort", choices=["score", "rate", "budget"], default="score",
                     help="score = rate x remaining budget x familiarity (default)")
    cd_.add_argument("--add", action="store_true",
                     help="store the shown campaigns (ids disc:...) + launch alerts")
    cc = csub.add_parser(
        "check",
        help="compliance gate: pre-flight a clip + caption against a campaign's rules",
    )
    cc.add_argument("video")
    cc.add_argument("--campaign", required=True, help="stored campaign id")
    cc.add_argument("--caption", help="the full text that will be posted with the clip")
    cc.add_argument("--platform", choices=["tiktok", "youtube", "instagram", "x", "facebook"])
    cc.add_argument("--source", help="source URL of the footage")
    cc.add_argument("--credit", help="credit text burned into the clip")
    p.set_defaults(func=_cmd_campaigns)

    p = sub.add_parser(
        "submissions",
        help="track Whop submissions: pending -> approved (48h) -> paid, earnings rollup",
    )
    ssub2 = p.add_subparsers(dest="submissions_action", required=True)
    sa = ssub2.add_parser("add", help="record a submission made through the Whop web flow")
    sa.add_argument("campaign", help="stored campaign id")
    sa.add_argument("url", help="the posted clip's URL (as submitted)")
    sa.add_argument("--platform", choices=["tiktok", "youtube", "instagram", "x", "facebook"])
    sa.add_argument("--account", help="posting account label")
    sa.add_argument("--title")
    sl = ssub2.add_parser("list")
    sl.add_argument("--status", choices=["pending", "approved", "rejected", "paid"])
    sl.add_argument("--campaign")
    sp_ = ssub2.add_parser("approve", help="brand approved the submission")
    sp_.add_argument("id", type=int)
    sj = ssub2.add_parser("reject", help="brand rejected it (reason feeds scoring)")
    sj.add_argument("id", type=int)
    sj.add_argument("--reason", required=True)
    sd = ssub2.add_parser("paid", help="payout landed - record the actual amount")
    sd.add_argument("id", type=int)
    sd.add_argument("--amount", type=float, required=True)
    sd.add_argument("--views", type=int, help="final verified view count")
    sv = ssub2.add_parser("views", help="update a submission's view count")
    sv.add_argument("id", type=int)
    sv.add_argument("views", type=int)
    ssub2.add_parser("sync", help="advance pending submissions past the 48h window")
    ssub2.add_parser("stats", help="earnings dashboard: per-campaign revenue, CPM, rejection rate")
    sr2 = ssub2.add_parser("reconcile", help="tracker totals vs Whop payouts/balance (read-only)")
    sr2.add_argument("--user", help="Whop user id (user_xxx) for payout history")
    sr2.add_argument("--ledger", help="ledger account id (ldgr_xxx) for balance")
    p.set_defaults(func=_cmd_submissions)

    p = sub.add_parser("vods", help="list a streamer's recent VODs")
    p.add_argument("streamer")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=_cmd_vods)

    args = parser.parse_args(argv)
    cfg = config.load(args.config)
    from .roster import PermissionError_

    try:
        return args.func(args, cfg)
    except PermissionError_ as e:
        print(str(e), file=sys.stderr)
        return 2
    except (ValueError, LookupError) as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
