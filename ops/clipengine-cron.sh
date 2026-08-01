#!/usr/bin/env bash
# Cron wrapper for clipengine jobs: loads the operator env file, prevents
# overlapping runs of the same job, and appends timestamped output to a log.
#
# Usage: clipengine-cron.sh <job-name> <clipengine args...>
#   e.g. clipengine-cron.sh campaigns-sync campaigns sync
#
# Environment:
#   CLIPENGINE_ENV_FILE  env file sourced before running (default ~/.clipengine/env;
#                        see ops/env.example - API keys live there, never in crontab)
#   CLIPENGINE_CONFIG    config TOML passed as --config when set
#   CLIPENGINE_LOG_DIR   log/lock directory (default ~/.clipengine/logs)
set -euo pipefail

if [ $# -lt 2 ]; then
    echo "usage: $0 <job-name> <clipengine args...>" >&2
    exit 64
fi
name="$1"
shift

env_file="${CLIPENGINE_ENV_FILE:-$HOME/.clipengine/env}"
if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
fi

log_dir="${CLIPENGINE_LOG_DIR:-$HOME/.clipengine/logs}"
mkdir -p "$log_dir"

exec 9>"$log_dir/$name.lock"
if ! flock -n 9; then
    # previous run still going (e.g. a slow campaigns sync) - skip, don't stack
    exit 0
fi

if command -v clipengine >/dev/null 2>&1; then
    cmd=(clipengine)
else
    cmd=(python3 -m clipengine.cli)
fi
if [ -n "${CLIPENGINE_CONFIG:-}" ]; then
    cmd+=(--config "$CLIPENGINE_CONFIG")
fi

status=0
{
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ${cmd[*]} $*"
    "${cmd[@]}" "$@" 2>&1 || status=$?
    echo "=== exit $status"
} >> "$log_dir/$name.log"
exit "$status"
