# Requires: pip install yt-dlp
# Optional: ffmpeg in PATH for reliable MP4 outputs.
# Output:
# - videos under ./downloads/<channel>/<id> - <title>.mp4
# - thumbnails next to videos
# - ./downloads/haaangry_feed.json with: id, url(local), thumb_url(local), title, description, tags[], like_count, comment_count

import os, json, random, re
from pathlib import Path
from yt_dlp import YoutubeDL
from yt_dlp.utils import match_filter_func

TARGET_COUNT = 100
BASE_DIR = Path("downloads").resolve()
BASE_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE = BASE_DIR / "archive.txt"
FEED_JSON = BASE_DIR / "haaangry_feed.json"

# Broad and niche queries to maximize diversity
QUERIES = [
    # Styles
    "food review",
    "street food",
    "home cooking",
    "recipe shorts",
    "quick recipes",
    "budget meals",
    "fine dining plating",
    "camp cooking",
    "air fryer recipes",
    "instant pot recipes",
    "bbq grilling",
    "deep fried snacks",
    "baking dessert",
    "pastry lamination",
    "coffee brewing",
    "milk tea boba",
    "mocktail recipe",
    # Cuisines / dishes
    "ramen",
    "sushi",
    "pho",
    "bibimbap",
    "tacos birria",
    "ceviche",
    "pizza neapolitan",
    "burger smashburger",
    "fried chicken",
    "dumplings",
    "dim sum",
    "naan curry",
    "biryani",
    "pad thai",
    "tom yum",
    "sichuan noodles",
    "thai street food",
    "korean street food",
    "japanese street food",
    "mexican street food",
    "indian street food",
    "vietnamese street food",
    "ethiopian injera",
    "nigerian jollof",
    "middle eastern shawarma",
    "falafel",
    "greek gyro",
    "poutine",
    "pierogi",
    "arepas",
    "empanadas",
    # Dietary
    "vegan cooking",
    "vegetarian recipes",
    "gluten free baking",
    "keto recipe",
    "halal food",
    "kosher food",
    # Occasions
    "breakfast pancakes",
    "brunch ideas",
    "lunch bowl",
    "dinner ideas",
    "late night snacks",
    # Sweets
    "chocolate dessert",
    "cheesecake",
    "ice cream",
    "macarons",
    "tiramisu",
    "baklava",
    # Regional specialties
    "texas bbq",
    "carolina bbq",
    "louisiana gumbo",
    "new orleans beignets",
    "chicago deep dish",
    "nyc bagels",
    "hawaiian poke",
    "peruvian pollo a la brasa",
    "argentinian asado",
    "turkish pide",
    "lebanese manakish",
    "malaysian laksa",
    "singaporean chilli crab",
    "indonesian nasi goreng",
    "filipino adobo",
    "taiwanese beef noodle",
    "hong kong egg waffle",
    "sri lankan kottu roti",
    "pakistani nihari",
    "bangladeshi bhuna",
    "nepalese momo",
    "uzbek plov",
    "moroccan tagine",
    "south african bunny chow",
    "jamaican jerk chicken",
    "trinidad doubles",
    "brazilian feijoada",
    "colombian arequipe",
    "venezuelan cachapas",
    # Drinks + extras
    "smoothie bowl",
    "fresh juice",
    "cocktail recipes easy",
]

random.shuffle(QUERIES)

# Helper: find a thumbnail file near a given video file
def find_thumbnail_for(video_path: Path) -> str | None:
    base = video_path.with_suffix("")  # strip extension
    folder = video_path.parent
    candidates = list(folder.glob(base.name + ".*"))
    for c in candidates:
        if c.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            return str(c)
    # Fallback: any image in the folder that includes the YouTube ID
    m = re.search(r"([A-Za-z0-9_-]{11})", video_path.name)
    if m:
        vid = m.group(1)
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            for c in folder.glob(f"*{vid}*{ext}"):
                return str(c)
    return None

def unique_tags(entry, query):
    tags = set()
    for k in ("tags", "categories", "keywords"):
        v = entry.get(k) or []
        if isinstance(v, str):
            v = [v]
        for t in v:
            if isinstance(t, str):
                tt = t.strip()
                if tt:
                    tags.add(tt)
    # include query term for traceability
    for t in query.lower().split():
        if len(t) > 2:
            tags.add(t)
    return sorted(tags)[:20]

def pick_file_path(entry) -> Path | None:
    # yt-dlp provides the final path under requested_downloads[*].filepath when download=True
    for rd in entry.get("requested_downloads", []) or []:
        fp = rd.get("filepath") or rd.get("_filename")
        if fp:
            return Path(fp)
    # fallback
    fp = entry.get("_filename") or entry.get("filename")
    return Path(fp) if fp else None

opts = {
    "paths": {"home": str(BASE_DIR)},
    "outtmpl": {
        "default": "%(uploader_id|uploader)s/%(id)s - %(title).80s.%(ext)s"
    },
    "format": "mp4/bestvideo*+bestaudio/best",
    "merge_output_format": "mp4",
    "noplaylist": True,
    "ignoreerrors": True,
    "quiet": True,
    "no_warnings": True,
    "writethumbnail": True,
    "writeinfojson": True,
    "download_archive": str(ARCHIVE),
    "match_filter": match_filter_func("duration <= 90 & is_live = false"),
    "postprocessors": [
        {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
    ],
    "max_downloads": TARGET_COUNT,  # hard stop at 100 successful downloads
}

dataset = []
seen_ids = set()

with YoutubeDL(opts) as ydl:
    for q in QUERIES:
        if len(dataset) >= TARGET_COUNT:
            break

        # Mix relevance and recency for variety
        for mode in ("ytsearch15", "ytsearchdate10"):
            if len(dataset) >= TARGET_COUNT:
                break
            search_url = f"{mode}:{q}"
            result = ydl.extract_info(search_url, download=True)
            if not result:
                continue
            for entry in result.get("entries", []) or []:
                if not entry or entry.get("_type") in {"url", "playlist"}:
                    continue
                vid = entry.get("id")
                if not vid or vid in seen_ids:
                    continue
                # Duration guard (secondary)
                dur = entry.get("duration")
                if dur and dur > 90:
                    continue

                file_path = pick_file_path(entry)
                if not file_path or not file_path.exists():
                    continue

                thumb_local = find_thumbnail_for(file_path)
                # Local URLs for fixtures
                local_video_url = str(file_path.resolve())
                local_thumb_url = str(Path(thumb_local).resolve()) if thumb_local else None

                item = {
                    "id": vid,
                    "url": local_video_url,
                    "thumb_url": local_thumb_url,
                    "title": (entry.get("title") or "").strip(),
                    "description": (entry.get("description") or "").strip(),
                    "tags": unique_tags(entry, q),
                    "like_count": entry.get("like_count"),
                    "comment_count": entry.get("comment_count"),
                }
                dataset.append(item)
                seen_ids.add(vid)
                if len(dataset) >= TARGET_COUNT:
                    break

# Persist the feed fixture in your expected schema
FEED_JSON.write_text(json.dumps({"videos": dataset}, ensure_ascii=False, indent=2))
print(f"Collected {len(dataset)} videos")
print(f"Feed written to: {FEED_JSON}")
