#!/usr/bin/env bash
# Fightland batch 01: ten variants from two source clips - "one scene, five
# doors". Each source is cut at five in-points (opener / early / mid / late /
# climax); the in-point decides the post's focus, the hook archetype matches
# the door, and every variant gets a distinct caption (campaign anti-spam rule
# + our archetype A/B). Audio is never altered - windows only.
#
# Usage:  bash examples/fightland_batch.sh
# Env:    SRC1/SRC2 source files, OUT output dir, CAMPAIGN id (defaults below)
set -euo pipefail

SRC1="${SRC1:-fightland/ftl1_3634005_035_pblt.mov}"
SRC2="${SRC2:-fightland/ftl1_3634032_035_pblt.mov}"
OUT="${OUT:-fightland/batch01}"
CAMPAIGN="${CAMPAIGN:-disc:fightland}"
mkdir -p "$OUT"
manifest="$OUT/posting-plan.txt"
: > "$manifest"

dur_s() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1" | cut -d. -f1; }

render() { # src start end hook caption outfile
    local src="$1" start="$2" end="$3" hook="$4" caption="$5" outfile="$6"
    if [ $((end - start)) -lt 12 ]; then
        echo "skip $outfile: window shorter than 12s (source too short for this door)"
        return 0
    fi
    echo "== $outfile  [${start}s-${end}s]  hook: $hook"
    clipengine repurpose "$src" -o "$OUT/$outfile" --no-captions \
        --campaign "$CAMPAIGN" --platform tiktok \
        --start "$start" --end "$end" \
        --hook "$hook" --caption "$caption"
    {
        echo "$outfile"
        echo "  window: ${start}s-${end}s of $(basename "$src")"
        echo "  hook:    $hook"
        echo "  caption: $caption"
        echo
    } >> "$manifest"
}

batch_for() { # src prefix c1..c5 h1..h5
    local src="$1" prefix="$2"
    local d; d="$(dur_s "$src")"
    local p20=$((d * 20 / 100)) p40=$((d * 40 / 100)) p60=$((d * 60 / 100))
    local tail_start=$((d > 30 ? d - 30 : 0))
    render "$src" 0 "$((d < 30 ? d : 30))"                    "$3" "$8"  "${prefix}_1_opener.mp4"
    render "$src" "$p20" "$((p20 + 25 < d ? p20 + 25 : d))"   "$4" "$9"  "${prefix}_2_early.mp4"
    render "$src" "$p40" "$((p40 + 25 < d ? p40 + 25 : d))"   "$5" "${10}" "${prefix}_3_mid.mp4"
    render "$src" "$p60" "$((p60 + 25 < d ? p60 + 25 : d))"   "$6" "${11}" "${prefix}_4_late.mp4"
    render "$src" "$tail_start" "$d"                          "$7" "${12}" "${prefix}_5_climax.mp4"
}

T="@STARZ @StarzBlockParty #ad"

batch_for "$SRC1" "clipA" \
    "new series alert 🚨" \
    "this scene sold me in 10 seconds" \
    "watch this without getting chills" \
    "the tension in this scene is unreal" \
    "nobody was ready for this scene" \
    "new obsession unlocked: Fightland on $T" \
    "50 Cent's new show Fightland just dropped on $T and it goes HARD" \
    "me cancelling my plans to binge Fightland on $T" \
    "if this scene doesn't get you watching Fightland on $T, nothing will" \
    "who else already started Fightland on @STARZ? @StarzBlockParty #ad"

batch_for "$SRC2" "clipB" \
    "your next binge just dropped" \
    "50 Cent did it again" \
    "the most intense new drama on TV" \
    "you're about to be obsessed with this show" \
    "this ending though 🤯" \
    "Fightland on @STARZ is the drama everyone's about to be talking about @StarzBlockParty #ad" \
    "not me rewinding this Fightland scene three times... $T" \
    "the new Fightland series on @STARZ did NOT come to play @StarzBlockParty #ad" \
    "Fightland on @STARZ just took over my whole feed @StarzBlockParty #ad" \
    "POV: you found your new favourite show. Fightland on $T"

echo
echo "done - posting plan written to $manifest"
echo "BEFORE POSTING: watch every variant. If one opens mid-sentence, its"
echo "context is broken - adjust --start by a couple of seconds and re-render."
echo "Spread posts over days (1-2/day per page); log each with:"
echo "  clipengine submissions add $CAMPAIGN '<post url>' --platform tiktok"
