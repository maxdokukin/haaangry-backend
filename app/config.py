import os
from pathlib import Path

# Path to the JSON you showed. Override with env FEED_JSON if needed.
FEED_JSON = Path(os.environ.get("FEED_JSON", "./data/videos.json")).resolve()

# Optional hard override for downloads folder. Otherwise auto-detected from JSON.
DOWNLOAD_DIR_ENV = os.environ.get("DOWNLOAD_DIR")
DOWNLOAD_DIR = Path(DOWNLOAD_DIR_ENV).resolve() if DOWNLOAD_DIR_ENV else None

# Demo profile
PROFILE = {
    "user_id": "u1",
    "name": "Alex",
    "credits_balance_cents": 3000,
    "default_address": {"line1": "1 Market St", "city": "SF", "state": "CA", "zip": "94105"},
}
