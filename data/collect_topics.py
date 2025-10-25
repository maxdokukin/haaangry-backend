# pip install -U yt-dlp
import yt_dlp
import json
import re
from typing import Dict, Any, List

VERBOSE = True
MAX_RESULTS = 10
MAX_COMMENTS = 20  # cap to avoid giant files
DURATION_MAX = 180  # seconds

SHORTS_RE = re.compile(r"\bshorts\b", re.IGNORECASE)

# ---------- SEARCH (unchanged logic) ----------
def get_youtube_links(search_query: str, max_results: int) -> List[Dict[str, Any]]:
    ydl_opts = {
        'quiet': not VERBOSE,
        'verbose': VERBOSE,
        'no_warnings': not VERBOSE,
        'extract_flat': True,
        'skip_download': True,
        'noplaylist': True,
    }
    search_url = f"ytsearch{max_results}:{search_query}"
    if VERBOSE:
        print(f"[search] {search_url}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(search_url, download=True)

    items = []
    for idx, entry in enumerate((result.get('entries') or []), 1):
        vid = entry.get('id')
        if not vid:
            if VERBOSE: print(f"[skip] {search_query} item#{idx}: missing id")
            continue

        title = entry.get('title') or ""
        desc  = entry.get('description') or ""
        dur   = int(entry.get('duration') or 0)

        if dur <= 0:
            if VERBOSE: print(f"[skip] {search_query} {vid}: no duration")
            continue
        if dur > DURATION_MAX:
            if VERBOSE: print(f"[skip] {search_query} {vid}: duration {dur}s > {DURATION_MAX}s")
            continue
        # If you want to enforce the keyword, uncomment:
        # if not SHORTS_RE.search(f"{title}\n{desc}"): continue

        link = f"https://www.youtube.com/watch?v={vid}"
        items.append({"id": vid, "url": link, "title": title, "description": desc, "duration_seconds": dur})
    if VERBOSE:
        print(f"[found] {search_query}: {len(items)} items kept after duration filter")
    return items

# ---------- ENRICH PER VIDEO (no search logic change) ----------
def enrich_video(url: str) -> Dict[str, Any]:
    # Ask yt-dlp for full metadata, including comments and caption track metadata.
    # We do NOT download media files.
    meta_opts = {
        'quiet': not VERBOSE,
        'verbose': VERBOSE,
        'no_warnings': not VERBOSE,
        'skip_download': True,
        'noplaylist': True,
        'extract_flat': False,
        # comments control
        'extractor_args': {
            'youtube': {
                # pass values as strings inside lists per yt-dlp API convention
                'max_comments': [str(MAX_COMMENTS)],
                'comment_sort': ['top'],  # or 'new'
            }
        },
    }
    try:
        with yt_dlp.YoutubeDL(meta_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        if VERBOSE: print(f"[meta-fail] {url}: {e}")
        return {}

    # Core fields
    out = {
        "url": url,
        "id": info.get("id"),
        "title": info.get("title") or "",
        "description": info.get("description") or "",
        "duration_seconds": int(info.get("duration") or 0),
        "upload_date": info.get("upload_date"),  # YYYYMMDD if present
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "tags": info.get("tags") or [],
        "categories": info.get("categories") or [],
        "channel": info.get("channel") or info.get("uploader") or "",
        "channel_id": info.get("channel_id") or info.get("channel_url"),
        "uploader": info.get("uploader"),
        "uploader_id": info.get("uploader_id"),
        "webpage_url": info.get("webpage_url"),
        "thumbnail": info.get("thumbnail"),
    }

    # Captions metadata (tracks only; not the text)
    # Both manual subtitles and automatic captions may be present
    subs = info.get("subtitles") or {}
    # autos = info.get("automatic_captions") or {}
    def pack_tracks(d):
        tracks = []
        for lang, items in d.items():
            for it in items or []:
                tracks.append({
                    "lang": lang,
                    "ext": it.get("ext"),
                    "name": (it.get("name") or {}).get("simpleText") if isinstance(it.get("name"), dict) else it.get("name"),
                    "url": it.get("url"),
                })
        return tracks
    out["captions"] = pack_tracks(subs)
    # out["auto_captions"] = pack_tracks(autos)

    # Shallow comments
    # Each comment in yt-dlp info typically has: id, text, author, author_id, like_count, published, timestamp
    raw_comments = info.get("comments") or []
    comments = []
    for c in raw_comments[:MAX_COMMENTS]:
        comments.append({
            "id": c.get("id"),
            "text": c.get("text"),
            "author": c.get("author"),
            "author_id": c.get("author_id"),
            "like_count": c.get("like_count"),
            "published": c.get("published"),
            "timestamp": c.get("timestamp"),
        })
    out["comments"] = comments

    return out

# ---------- TOPICS ----------
TOPICS = [
    "food review","street food","home cooking","recipe shorts","quick recipes","budget meals",
    "fine dining plating","camp cooking","air fryer recipes","instant pot recipes","bbq grilling",
    "deep fried snacks","baking dessert","pastry lamination","coffee brewing","milk tea boba",
    "mocktail recipe","ramen","sushi","pho","bibimbap","birria tacos","ceviche","neapolitan pizza",
    "smashburger","fried chicken","dumplings","dim sum","curry naan","biryani","pad thai","tom yum",
    "sichuan noodles","thai street food","korean street food","japanese street food","mexican street food",
    "indian street food","vietnamese street food","ethiopian injera","nigerian jollof","shawarma","falafel",
    "gyro","poutine","pierogi","arepas","empanadas","vegan cooking","vegetarian recipes","gluten free baking",
    "keto recipe","halal food","kosher food","breakfast pancakes","brunch ideas","lunch bowl","dinner ideas",
    "late night snacks","chocolate dessert","cheesecake","ice cream","macarons","tiramisu","baklava",
    "texas bbq","carolina bbq","gumbo","beignets","deep dish pizza","nyc bagels","poke bowl","pollo a la brasa",
    "asado","turkish pide","manakish","laksa","chilli crab","nasi goreng","filipino adobo","taiwanese beef noodle",
    "egg waffle","kottu roti","nihari","bhuna","momo","plov","moroccan tagine","bunny chow","jerk chicken",
    "trinidad doubles","feijoada","cachapas","smoothie bowl","fresh juice","easy cocktails"
]

def main():
    out = {}
    total = 0
    for topic in TOPICS:
        base_items = get_youtube_links(topic, MAX_RESULTS)
        enriched = []
        for it in base_items:
            e = enrich_video(it["url"])
            if not e:
                # fallback to base fields if enrichment failed
                e = it
            # enforce duration again if enrichment changed it
            dur = int(e.get("duration_seconds") or it["duration_seconds"] or 0)
            if 0 < dur <= DURATION_MAX:
                enriched.append(e)
        out[topic] = enriched
        total += len(enriched)
        if VERBOSE:
            print(f"[topic] {topic}: {len(enriched)} items written")

    outfile = "youtube_video_links_enriched.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[done] wrote {outfile} with {total} total items")

if __name__ == "__main__":
    main()
