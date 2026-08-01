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


def _cmd_publish(args: argparse.Namespace, cfg: config.Config) -> int:
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

    manifest = pipeline.process_vod(
        args.video,
        args.chat,
        args.streamer,
        args.output_dir,
        cfg,
        top_n=args.top,
        with_captions=not args.no_captions,
        facecam=facecam,
    )
    rendered = [m for m in manifest if m["status"] == "rendered"]
    for m in manifest:
        if m["status"] == "rendered":
            mute_note = (
                f"  (muted {len(m['muted_segments'])} music segment(s))"
                if m.get("muted_segments")
                else ""
            )
            print(f"#{m['index']} {m['start']:8.1f}-{m['end']:8.1f}s "
                  f"score={m['score']:.2f}  {m['path']}{mute_note}")
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
                title = m.get("suggested_title") or args.title_template.format(
                    streamer=m["streamer"], i=m["index"], start=int(m["start"])
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

    with CampaignStore(cfg.campaigns.campaigns_db) as store:
        if args.campaigns_action == "sync":
            from .campaigns import alerts
            from .campaigns.whop import WhopClient, WhopError

            try:
                client = WhopClient(cfg.campaigns.api_key)
            except WhopError as e:
                print(str(e), file=sys.stderr)
                return 2
            fetched: list[Campaign] = []
            for status in cfg.campaigns.statuses:
                fetched.extend(
                    client.campaigns(
                        status=status,
                        goal_types=tuple(cfg.campaigns.goal_types) or None,
                        with_rules=not args.no_rules,
                    )
                )
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
            if not c.rules_text:
                print("no rules text stored - re-sync without --no-rules or add --rules")
                return 1
            _print_checklist(parse_rules(c.rules_text))
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
    p.set_defaults(func=_cmd_render)

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
    p.set_defaults(func=_cmd_campaigns)

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


if __name__ == "__main__":
    raise SystemExit(main())
