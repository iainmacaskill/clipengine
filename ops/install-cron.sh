#!/usr/bin/env bash
# Idempotently install (or update) the clipengine cron jobs in the current
# user's crontab. The jobs live between marker lines; re-running replaces the
# block, and everything else in the crontab is left untouched.
#
#   ops/install-cron.sh            install/update the three sync jobs
#   ops/install-cron.sh --with-queue-run   also cron 'queue run' every 15 min
#   ops/install-cron.sh --remove   remove the block
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
wrapper="$here/clipengine-cron.sh"
begin="# >>> clipengine jobs (managed by install-cron.sh) >>>"
end="# <<< clipengine jobs <<<"

if ! command -v crontab >/dev/null 2>&1; then
    echo "crontab not found - install cron, or copy ops/crontab.example into" >&2
    echo "your scheduler of choice (systemd timers, launchd, ...)" >&2
    exit 1
fi
[ -x "$wrapper" ] || chmod +x "$wrapper"

block="$begin
*/10 * * * * $wrapper campaigns-sync campaigns sync
0 * * * * $wrapper submissions-sync submissions sync
15 6 * * * $wrapper stats-sync stats sync"
if [ "${1:-}" = "--with-queue-run" ]; then
    block="$block
*/15 * * * * $wrapper queue-run queue run"
fi
block="$block
$end"

current="$(crontab -l 2>/dev/null || true)"
cleaned="$(printf '%s\n' "$current" | awk -v b="$begin" -v e="$end" '
    $0 == b {skip = 1; next}
    $0 == e {skip = 0; next}
    !skip {print}
')"

if [ "${1:-}" = "--remove" ]; then
    printf '%s\n' "$cleaned" | crontab -
    echo "clipengine cron jobs removed"
    exit 0
fi

printf '%s\n%s\n' "$cleaned" "$block" | crontab -
echo "installed - current crontab:"
crontab -l
echo
echo "next: copy ops/env.example to ~/.clipengine/env (chmod 600) and fill in"
echo "CLIPENGINE_WHOP_API_KEY + CLIPENGINE_CONFIG; logs land in ~/.clipengine/logs/"
