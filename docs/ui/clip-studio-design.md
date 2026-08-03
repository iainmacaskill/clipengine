# Clip Studio — UI design for the no-terminal workflow

`clip-studio-mockup.html` is the original clickable design mockup (static, no
backend). The **working** version is now shipped in `clipengine/web/` and runs
against the real engine.

## Running it

```bash
pip install -e '.[web]'      # server is stdlib-only; [web] adds asr + yt-dlp
clipengine web               # http://127.0.0.1:8765  (--host/--port to change)
```

Open the printed URL in a browser. The page talks to a small JSON API
(`clipengine/web/api.py`) served by a dependency-free stdlib HTTP server
(`clipengine/web/server.py`). Long tasks (download, transcribe, detect, render)
run on background threads and the page polls `GET /api/jobs/<id>`. Source
videos are tracked in their own `sources.db` beside `campaigns.db` — the live
campaign store's schema is never touched.

This doc maps each screen to the engine pieces it drives.

## Who it's for

A user who cannot (or won't) use the terminal. The flow starts at "New
campaign found" and ends with rendered files + captions ready for manual
TikTok upload. Every screen has exactly one primary action; jargon is
translated (no "repurpose", "gate", "CPM" without explanation).

## Screens → engine mapping

| # | Screen | What the user does | Engine behind it |
|---|--------|--------------------|------------------|
| 1 | New campaign | Sees scored campaign cards, picks one | `campaigns discover` / `campaigns sync` + `score.rank` (cron feeds the inbox) |
| 2 | The rules | Reads the translated rule checklist, accepts | `rules.parse_rules` checklist; "automatic" chips = `template.build_caption` tokens; accept = `campaigns add --id disc:<slug> --rules-file …` |
| 3 | Source videos | Pastes approved links / drops files, watches download+transcribe | yt-dlp download; `pipeline.source_transcript` (cached beside file); approved-source check = `gate` source rule |
| 4 | Best moments | Ticks/unticks detected windows, reads transcript excerpts | `detect` (audio energy) + `models.Transcript.text_between` for excerpts; tags are editorial curation |
| 5 | Make the clips | Edits hook (`*word*` = highlight), picks a look, sees locked caption | `textcard.PRESETS` for style chips; caption preview = `build_caption` with required tokens rendered as locked chips; snap note = `snap_to_speech` |
| 6 | Ready to post | Watches render, copies caption, marks posted | `repurpose_asset` (single-encode path); PASSED CHECK = `gate.preflight`; "mark as posted" = `submissions add`; tracker states = pending → approved (48h) → paid |

## Design tokens

- Ground `#16151A`, panel `#1F1D24`, line `#34313D`, text `#EDEAF2`,
  muted `#9B96A8`.
- Accent `#FFD400` — deliberately the caption-highlight yellow from the
  "clean" render preset, so the UI shares the product's own visual DNA.
- Semantic green/red reserved for pass/fail and active/blocked states,
  never used as accent.
- Display face Archivo Black (already one of the caption fonts;
  embedded as a data URI in the mockup), body = system grotesque stack,
  `tabular-nums` on all money/time/score figures.
- Single dark theme, committed: it's an edit-bay tool and video
  previews must read true.

## Implementation notes (when we build it)

- Thinnest viable backend: a local FastAPI/Flask shim over the existing
  Python API (`campaigns`, `pipeline`, `submissions`), serving this page;
  no CLI subprocesses needed except yt-dlp.
- Long jobs (download, transcribe, render) report progress over a
  polling endpoint or SSE; transcribe-once caching already exists.
- The "risky for brand" tag on a moment is a human call; the UI keeps it
  one tap to include, with the warning pill as friction.
- Step 6's "Mark as posted" should open the tracker record with the URL
  field ready to paste, since Whop submission itself stays a manual web
  flow (no public API).
