import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any

from .schemas import Video

def _common_download_dir(records: List[Dict[str, Any]]) -> Path | None:
    paths = [Path(r.get("download_path","")) for r in records if r.get("download_path")]
    paths = [p for p in paths if p.exists()]
    if not paths:
        return None
    try:
        return Path(os.path.commonpath([str(p.parent) for p in paths]))
    except Exception:
        return paths[0].parent

def load_raw(json_path: Path) -> Tuple[List[Dict[str, Any]], Path | None]:
    data = json.loads(json_path.read_text())
    # flatten categories -> list
    items: List[Dict[str, Any]] = []
    for _, lst in data.items():
        if isinstance(lst, list):
            items.extend(lst)
    download_dir = _common_download_dir(items)
    return items, download_dir

def build_feed(items: List[Dict[str, Any]], base_url: str, mounted_prefix: str, mounted_dir: Path | None) -> List[Video]:
    out: List[Video] = []
    for r in items:
        vid = r.get("id") or r.get("video_id")
        title = r.get("title") or ""
        desc = r.get("description") or ""
        tags = r.get("tags") or []
        like_count = int(r.get("like_count") or 0)
        comment_count = int(r.get("comment_count") or 0)
        thumb = r.get("thumbnail") or r.get("thumb_url") or None

        video_url: str | None = None

        # Prefer local downloaded mp4 served via /videos
        dl = r.get("download_path")
        if dl:
            filename = Path(dl).name
            if mounted_dir and (mounted_dir / filename).exists():
                video_url = f"{base_url.rstrip('/')}{mounted_prefix}/{filename}"

        # Fallback: if no local file, skip the record (YouTube watch pages won't play in AVPlayer)
        if not video_url:
            continue

        out.append(Video(
            id=str(vid),
            url=video_url,
            thumb_url=thumb,
            title=title,
            description=desc,
            tags=tags if isinstance(tags, list) else [],
            like_count=like_count,
            comment_count=comment_count,
        ))
    return out
