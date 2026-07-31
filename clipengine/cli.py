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
