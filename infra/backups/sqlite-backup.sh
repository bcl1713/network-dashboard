#!/usr/bin/env bash
# Hot-backup the engine SQLite filter store using `sqlite3 .backup`, which
# is WAL-aware. Rotates 7 daily and 4 weekly snapshots.
#
# Run on the host (not inside the engine container) so the snapshots end up
# alongside the rest of the infra. Schedule with cron or Portainer.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")"/../.. && pwd)"
DB_PATH="${ENGINE_DB_PATH_HOST:-$REPO_ROOT/infra/data/engine/filters.db}"
SNAP_DIR="${SNAP_DIR:-$REPO_ROOT/infra/backups/snapshots}"

mkdir -p "$SNAP_DIR"

if [[ ! -f "$DB_PATH" ]]; then
  echo "no DB at $DB_PATH; nothing to back up" >&2
  exit 0
fi

today="$(date +%Y%m%d)"
daily="$SNAP_DIR/filters-$today.sqlite"

# sqlite3 .backup tolerates concurrent writers; falls back to cp if the binary
# is missing.
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".backup '$daily'"
else
  cp -- "$DB_PATH" "$daily"
fi

# Daily rotation: keep last 7.
mapfile -t dailies < <(find "$SNAP_DIR" -maxdepth 1 -name 'filters-????????.sqlite' -printf '%f\n' | sort)
if (( ${#dailies[@]} > 7 )); then
  for f in "${dailies[@]:0:${#dailies[@]}-7}"; do
    rm -f -- "$SNAP_DIR/$f"
  done
fi

# Weekly rotation on Sundays: copy today's daily into a dated weekly slot.
if [[ "$(date +%u)" == "7" ]]; then
  weekly="$SNAP_DIR/filters-week-$today.sqlite"
  cp -- "$daily" "$weekly"
  mapfile -t weeklies < <(find "$SNAP_DIR" -maxdepth 1 -name 'filters-week-????????.sqlite' -printf '%f\n' | sort)
  if (( ${#weeklies[@]} > 4 )); then
    for f in "${weeklies[@]:0:${#weeklies[@]}-4}"; do
      rm -f -- "$SNAP_DIR/$f"
    done
  fi
fi

echo "backup ok: $daily"
