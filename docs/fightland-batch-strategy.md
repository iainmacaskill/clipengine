# Fightland batch 01 — "one scene, five doors" strategy

Applies [the caption playbook](caption-playbook.md) to the Fightland campaign:
ten variants from two official source clips, produced by
[`examples/fightland_batch.sh`](../examples/fightland_batch.sh).

## The in-point is the editorial decision

The campaign forbids touching the audio or context, so with fixed footage the
strongest variable left is **where the clip starts**. The first frame decides
what the post is about — whoever is on screen at second 0 is the subject, and
the emotional temperature at the in-point sets the register the hook must
match:

| Door | Window | Feel | Hook archetype |
|---|---|---|---|
| 1 opener | first ~30s | scene-setting | urgency/news |
| 2 early | from ~20% | character-forward | bold opinion |
| 3 mid | from ~40% | in-the-tension | challenge |
| 4 late | from ~60% | escalation | tension/curiosity (must pay off) |
| 5 climax | last ~30s | cold-open at the payoff | bold claim |

Five doors x two sources = ten posts, no repeated hook or caption (campaign
anti-spam rule; also our A/B design).

## The experiment

Each variant pairs one door with one hook archetype and one caption from the
playbook bank. After posting, `submissions add` each URL, update views after
48h (`submissions views`), and `submissions stats` becomes the readout: which
door x archetype earns views and engagement. That result seeds the next batch
(double down on the winning door/archetype) — the M4 optimisation loop running
on real campaign data.

## Operating rules (from the campaign brief)

- Watch every variant before posting: a window that opens mid-sentence has
  broken context - shift `--start` a couple of seconds and re-render.
- Audio untouched; only windows, on-screen text, and captions vary.
- Spread posts: 1-2 per day per page, TikTok + Instagram (IG captions tag
  only @STARZ). Same video never more than 5 times across pages.
- Every caption carries Fightland + Starz + required tags + #ad.
- Posts stay live >= 30 days; no boosting of any kind.
