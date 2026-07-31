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
    x, y, w, h = (int(v) for v in args.facecam.split(","))
    candidate = ClipCandidate(start=args.start, end=args.end, score=0.0)
    out = pipeline.render_candidate(
        args.video,
        candidate,
        FacecamRegion(x, y, w, h),
        args.output,
        cfg,
        with_captions=not args.no_captions,
    )
    print(out)
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
    p.add_argument("--facecam", required=True, help="facecam ROI in source px: X,Y,W,H")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--no-captions", action="store_true")
    p.set_defaults(func=_cmd_render)

    p = sub.add_parser("vods", help="list a streamer's recent VODs")
    p.add_argument("streamer")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=_cmd_vods)

    args = parser.parse_args(argv)
    cfg = config.load(args.config)
    return args.func(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
