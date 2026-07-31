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
    rr = rsub.add_parser("revoke", help="revoke a streamer's permission (immediate)")
    rr.add_argument("streamer")
    rr.add_argument("--reason")
    rc = rsub.add_parser("check", help="check whether ingestion is allowed")
    rc.add_argument("streamer")
    rl = rsub.add_parser("list")
    rl.add_argument("--status", choices=["allowed", "revoked"])
    p.set_defaults(func=_cmd_roster)

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
