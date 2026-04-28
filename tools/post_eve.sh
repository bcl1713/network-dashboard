#!/usr/bin/env bash
# Post a single EVE JSON event to the engine. Used by `make smoke`.
#
# Usage: tools/post_eve.sh path/to/event.json [engine_url]
#
# Reads the API token from $ENGINE_API_TOKEN or the .env file in the repo root.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <event.json> [engine_url]" >&2
  exit 2
fi

event_file=$1
engine_url=${2:-http://10.10.50.13:8081}

if [[ -z "${ENGINE_API_TOKEN:-}" ]]; then
  if [[ -f .env ]]; then
    # shellcheck disable=SC1091
    set -a; source .env; set +a
  fi
fi

if [[ -z "${ENGINE_API_TOKEN:-}" ]]; then
  echo "ENGINE_API_TOKEN is not set (export it or add it to .env)" >&2
  exit 2
fi

if [[ ! -f "$event_file" ]]; then
  echo "event file not found: $event_file" >&2
  exit 2
fi

curl -fsS \
  -H "X-API-Token: $ENGINE_API_TOKEN" \
  -H 'Content-Type: application/json' \
  --data @"$event_file" \
  "$engine_url/ingest/event"
echo
