#!/usr/bin/env bash
# Start the engine locally without Docker.  Useful on hosts where Docker is
# unavailable (e.g. TrueNAS, bare-metal dev boxes).
#
# Usage: tools/dev-engine.sh [port]
#   port  defaults to 8081 (same as ENGINE_HOST_PORT in docker-compose)
#
# Prerequisites: pip install -e services/engine  (installs uvicorn + deps)
#
# Settings are read from $ENGINE_API_TOKEN or the repo-root .env file.
# ENGINE_DB_PATH is defaulted to infra/data/engine/filters.db so the
# Docker-only /data path is never required.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_DIR="$REPO_ROOT/services/engine"
PORT="${1:-8081}"

# Load .env from repo root if the token isn't already in the environment.
if [[ -z "${ENGINE_API_TOKEN:-}" && -f "$REPO_ROOT/.env" ]]; then
    set -a; source "$REPO_ROOT/.env"; set +a
fi

if [[ -z "${ENGINE_API_TOKEN:-}" ]]; then
    echo "ENGINE_API_TOKEN is not set (export it or add it to .env)" >&2
    exit 2
fi

# Override the Docker-volume path with a local one when not already set.
if [[ -z "${ENGINE_DB_PATH:-}" || "$ENGINE_DB_PATH" == "/data/"* ]]; then
    export ENGINE_DB_PATH="$REPO_ROOT/infra/data/engine/filters.db"
fi

mkdir -p "$(dirname "$ENGINE_DB_PATH")"

echo "engine  → http://127.0.0.1:${PORT}"
echo "db      → $ENGINE_DB_PATH"
echo "loki    → ${ENGINE_LOKI_URL:-http://localhost:3100}  (push failures are non-fatal)"
echo ""

# alembic.ini must be in the working directory.
cd "$ENGINE_DIR"
exec uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --reload
