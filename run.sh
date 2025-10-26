#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   FEED_JSON="./data/videos.json" uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
#
# Or use this script with defaults:
#   ./run.sh

export FEED_JSON="${FEED_JSON:-./data/videos.json}"

# --- added: env + dirs + checks ---
# optional venv
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# load .env if present
if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# defaults
export DOWNLOAD_DIR="${DOWNLOAD_DIR:-./data/downloads}"

# ensure paths
mkdir -p "$(dirname "$FEED_JSON")" "$DOWNLOAD_DIR"

# sanity checks
if [ ! -f "$FEED_JSON" ]; then
  echo "[run.sh] FEED_JSON not found: $FEED_JSON" >&2
  exit 1
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[run.sh] Warning: ANTHROPIC_API_KEY not set. Claude features will fallback." >&2
fi

echo "[run.sh] FEED_JSON=$FEED_JSON"
echo "[run.sh] DOWNLOAD_DIR=$DOWNLOAD_DIR"
echo "[run.sh] Starting API…"
# --- end added ---

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
