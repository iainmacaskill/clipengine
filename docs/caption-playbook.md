# Caption & hook playbook — what performs on short-form clips

Distilled from 2026 caption-strategy research (OpusClip, ShareB, MarketerHire,
clip-farming guides) for use across campaigns. Two distinct surfaces:

- **on-screen hook text** — burned into the video's opening (our `--hook`);
  wins or loses the first ~1.3 seconds before the swipe
- **post caption** — the text field on TikTok/IG; feeds search + comments and
  carries campaign-required tags/mentions

## Principles (evidence-backed)

1. **The first 1.3 seconds decide.** The hook must state a reason to watch,
   front-loaded — a bold claim, question, or curiosity gap. Not a description.
2. **Curiosity must pay off.** "Wait for it" works only when the clip
   delivers; bait is banned by campaigns (and punished by the algorithm as
   low completion). Never promise what the footage doesn't show.
3. **Sound-off is the norm (~60%).** On-screen text has to carry meaning
   alone. Word-by-word burned captions outperform full sentences for
   completion on entertainment content (this is our `opus` caption style).
4. **3–7 word chunks** — readable at scroll speed. Long lines die.
5. **Caption structure:** strong first line → the searchable name (show,
   game, product — campaigns require it anyway) → one engagement action
   (a question that invites comments lifts comment counts materially).
6. **Opinion hype outperforms ad-speak.** "this sold me in 10 seconds" beats
   "don't miss the new series". Lowercase, casual, native tone; brands'
   own briefs (Cantina, Clipping Culture) explicitly ask for meme-post
   register, not promo copy.
7. **Vary hooks per post.** Same-video/same-caption reposting is both a
   campaign violation and an algorithmic dampener. Rotate hook archetypes.
8. **Tell viewers what to do next** — one CTA only, matched to the goal
   (watch/comment/save), never stacked.

## Hook archetypes that repeat across successful clip pages

| Archetype | Template | When |
|---|---|---|
| Bold opinion | "the best X I've seen in a long time" | strong standalone moment |
| Curiosity gap | "nobody expected what happens next" | clip with a real payoff |
| Urgency/news | "new X alert 🚨" / "X just dropped" | launches, premieres |
| POV/relatable | "POV: your next binge just found you" | lifestyle-adjacent |
| Challenge | "watch this without getting chills" | emotional/intense clips |
| Social proof | "everyone's talking about X" | trending subjects |
| Question | "who else is watching X already?" | drives comments |

## Compliance notes (campaign captions)

- Required names/tags/mentions go in every caption — the campaign template
  (`build_caption`) appends them automatically; write the human part first.
- Sponsored posts need FTC disclosure (#ad) — briefs increasingly say so
  explicitly.
- Engagement-fraud adjacency (bait phrasing with no payoff, "part 2 in
  comments" that doesn't exist) risks campaign bans, not just weak reach.

Sources: opus.pro/blog/tiktok-caption-subtitle-best-practices,
shareb.io/blog/tiktok-caption-strategy, marketerhire.com/blog/tiktok-captions,
ganknow.com/blog/clip-farming, schedpilot.com/viral-tiktok-caption-ideas-for-clips.

## On-screen typography (draft 2, implemented in edit/textcard.py)

What the standardised "clipper look" actually is - so consistent that CapCut,
Submagic, Opus Clip and Riverside all ship it as a preset:

- **Font**: Montserrat Bold/ExtraBold (Black 900 for single-word titles);
  any heavy geometric sans reads the same at a glance. White fill, thick
  black outline (~10% of font size) and/or a soft drop shadow so text
  survives any footage.
- **Layout**: short stacked lines (3-4 words), centre-aligned, hook in the
  top safe zone (clear of the right-side icon rail and bottom UI bar), CTA
  smaller at ~3/4 height.
- **Emphasis**: one keyword per hook in a highlight colour (yellow is the
  norm) - more than one kills the effect.
- **Emoji**: 1-3 max, placed to punctuate the hook, not decorate it. TikTok
  captions also support [shortcode] custom emojis. Note: ffmpeg drawtext
  cannot render colour emoji (empty boxes) - the textcard renderer exists
  partly for this.
- **Hook timing**: give the hook the full first 3 seconds; persistent top
  text is the norm on clip pages.

`clipengine repurpose` renders hook/CTA as text cards automatically when
Pillow is available; `*word*` marks the highlight, `CLIPENGINE_FONT_FILE`
points at a custom font (drop Montserrat ExtraBold into ~/Library/Fonts and
it is picked up first).

Typography sources: designyourway.net/blog/best-fonts-for-tiktok,
blitzcutai.com/blog/best-caption-fonts-tiktok, kapwing.com (TikTok fonts),
metricool.com/tiktok-emojs-code, signalytics.ai/tiktok-emojis-codes.

## Style presets (fonts + colours, implemented)

Who uses what, from the research - and the matching `--style` preset:

| Preset | Font | Accent | Modeled on | Fits |
|---|---|---|---|---|
| clean | Montserrat ExtraBold | yellow #FFD400 | the standard clipper preset | anything |
| hormozi | Anton, ALL CAPS | yellow #FFD93D | Alex Hormozi (The Bold Font) | opinions, claims |
| hormozi-green | Anton, ALL CAPS | green #A6FF00 | Hormozi money/positive alternate | value, "free", wins |
| beast | Bangers | red #FF3131 | MrBeast energy (Komika Axis isn't OFL) | shock, reactions |
| block | Archivo Black | red #FF3131 | heavy-statement pages | superlatives, urgency |
| playful | Luckiest Guy | pink #FF5CA8 | lifestyle/comedy pages | light moments |

Colour language: yellow = attention (the default), green = money/positive,
red = urgency/shock, pink = playful. One highlighted keyword only.
`clipengine fonts install` fetches the free (OFL/Apache) fonts from
google/fonts into ~/.clipengine/fonts; `clipengine fonts list` shows what
each preset resolves to. Rotating presets across a batch adds the variety
that per-page anti-spam rules and the door-x-style A/B both want -
docs/fightland-batch-strategy.md rotates all ten variants.

Preset sources: designyourway.net/blog/what-font-does-mrbeast-use (Komika
Axis), caply.io + ascynd.io Hormozi style guides (The Bold Font/Anton,
#FFD93D/#A6FF00, ALL CAPS, +15% engagement claims), blitzcutai.com caption
fonts survey.
