#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   FEED_JSON="./data/videos.json" uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
#
# Or use this script with defaults:
#   ./run.sh

export FEED_JSON="${FEED_JSON:-./data/videos.json}"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
