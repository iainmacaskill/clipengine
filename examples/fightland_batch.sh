#!/usr/bin/env bash
# Fightland batch: sweep EVERY source clip in the folder through the
# "one scene, five doors" strategy (docs/fightland-batch-strategy.md).
#
# Each source is cut at five in-points (opener/early/mid/late/climax). Hooks
# stay matched to their door's archetype and rotate across sources; captions
# and style presets cycle on different strides so no two posts repeat a
# combination. Windows snap to sentence boundaries (--snap); audio is never
# altered.
#
# Usage:  bash examples/fightland_batch.sh
# Env:    SRCDIR (default fightland)   folder of campaign source clips
#         EXT    (default mov)        source extension to sweep
#         OUT    (default $SRCDIR/batch01)
#         CAMPAIGN (default disc:fightland)
#         SNAP   (default --snap; set SNAP= to disable)
set -euo pipefail

SRCDIR="${SRCDIR:-fightland}"
EXT="${EXT-mov}"
OUT="${OUT:-$SRCDIR/batch01}"
CAMPAIGN="${CAMPAIGN:-disc:fightland}"
SNAP="${SNAP---snap}"
mkdir -p "$OUT"
manifest="$OUT/posting-plan.txt"
: > "$manifest"

T="@STARZ @StarzBlockParty #ad"

# door-matched hook pools (archetype fits the door's emotional temperature);
# the variant used rotates with the source index
HOOKS_1=("new *series* alert 🚨" "your next *binge* just dropped")                       # opener: urgency/news
HOOKS_2=("this scene *sold* me in 10 seconds" "50 Cent did it *again*")                 # early: bold opinion
HOOKS_3=("watch this without getting *chills*" "the most *intense* new drama on TV")    # mid: challenge
HOOKS_4=("the *tension* in this scene is unreal" "you're about to be *obsessed* with this show")  # late: build
HOOKS_5=("*nobody* was ready for this scene" "this *ending* though 🤯")                 # climax: payoff claim

CAPTIONS=(
    "new obsession unlocked: Fightland on $T"
    "50 Cent's new show Fightland just dropped on $T and it goes HARD"
    "me cancelling my plans to binge Fightland on $T"
    "who else already started Fightland on @STARZ? @StarzBlockParty #ad"
    "if this scene doesn't get you watching Fightland on $T, nothing will"
    "Fightland on @STARZ is the drama everyone's about to be talking about @StarzBlockParty #ad"
    "not me rewinding this Fightland scene three times... $T"
    "the new Fightland series on @STARZ did NOT come to play @StarzBlockParty #ad"
    "Fightland on @STARZ just took over my whole feed @StarzBlockParty #ad"
    "POV: you found your new favourite show. Fightland on $T"
)
STYLES=(clean hormozi hormozi-green beast block playful)

dur_s() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1" | cut -d. -f1; }

render() { # src start end style hook caption outfile
    local src="$1" start="$2" end="$3" style="$4" hook="$5" caption="$6" outfile="$7"
    if [ $((end - start)) -lt 12 ]; then
        echo "skip $outfile: window shorter than 12s (source too short for this door)"
        return 0
    fi
    echo "== $outfile  [${start}s-${end}s]  style: $style  hook: $hook"
    # shellcheck disable=SC2086
    clipengine repurpose "$src" -o "$OUT/$outfile" --no-captions $SNAP \
        --campaign "$CAMPAIGN" --platform tiktok --style "$style" \
        --start "$start" --end "$end" \
        --hook "$hook" --caption "$caption"
    {
        echo "$outfile"
        echo "  window: ${start}s-${end}s of $(basename "$src")  style: $style"
        echo "  hook:    $hook"
        echo "  caption: $caption"
        echo
    } >> "$manifest"
}

shopt -s nullglob
sources=("$SRCDIR"/*."$EXT")
if [ ${#sources[@]} -eq 0 ]; then
    echo "no .$EXT files in $SRCDIR/ - set SRCDIR/EXT" >&2
    exit 1
fi
echo "sweeping ${#sources[@]} source clip(s) x 5 doors = $((${#sources[@]} * 5)) variants"

s=0
for src in "${sources[@]}"; do
    d="$(dur_s "$src")"
    p20=$((d * 20 / 100)); p40=$((d * 40 / 100)); p60=$((d * 60 / 100))
    tail_start=$((d > 30 ? d - 30 : 0))
    tag=$(printf "clip%02d" $((s + 1)))
    for door in 1 2 3 4 5; do
        hooks_var="HOOKS_${door}[@]"
        hooks=("${!hooks_var}")
        hook="${hooks[$((s % ${#hooks[@]}))]}"
        # stride 7 is coprime with the pool size, so captions spread across
        # sources instead of repeating every second clip
        caption="${CAPTIONS[$(((s * 7 + (door - 1) * 3) % ${#CAPTIONS[@]}))]}"
        style="${STYLES[$(((s + door - 1) % ${#STYLES[@]}))]}"
        case $door in
            1) start=0;           end=$((d < 30 ? d : 30));            name="${tag}_1_opener.mp4" ;;
            2) start=$p20;        end=$((p20 + 25 < d ? p20 + 25 : d)); name="${tag}_2_early.mp4" ;;
            3) start=$p40;        end=$((p40 + 25 < d ? p40 + 25 : d)); name="${tag}_3_mid.mp4" ;;
            4) start=$p60;        end=$((p60 + 25 < d ? p60 + 25 : d)); name="${tag}_4_late.mp4" ;;
            5) start=$tail_start; end=$d;                               name="${tag}_5_climax.mp4" ;;
        esac
        render "$src" "$start" "$end" "$style" "$hook" "$caption" "$name"
    done
    s=$((s + 1))
done

echo
echo "done - ${#sources[@]} source(s) processed; posting plan: $manifest"
echo "BEFORE POSTING: watch every variant (snapping guarantees sentence"
echo "boundaries, not scene sense). Spread posts 1-2/day per page; log each:"
echo "  clipengine submissions add $CAMPAIGN '<post url>' --platform tiktok"
