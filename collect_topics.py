# pip install -U yt-dlp
import yt_dlp
import json
import re

VERBOSE = True  # toggle logs

SHORTS_RE = re.compile(r"\bshorts\b", re.IGNORECASE)

# --- unchanged search logic (ytsearch{max_results}:{query}) ---
def get_youtube_links(search_query, max_results):
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
        result = ydl.extract_info(search_url, download=False)

    items = []
    for idx, entry in enumerate((result.get('entries') or []), 1):
        vid = entry.get('id')
        if not vid:
            if VERBOSE:
                print(f"[skip] {search_query} item#{idx}: missing id")
            continue

        title = entry.get('title') or ""
        desc  = entry.get('description') or ""
        dur   = int(entry.get('duration') or 0)

        if dur <= 0:
            if VERBOSE:
                print(f"[skip] {search_query} {vid}: no duration")
            continue
        if dur > 180:
            if VERBOSE:
                print(f"[skip] {search_query} {vid}: duration {dur}s > 180s")
            continue
        text = f"{title}\n{desc}"
        # if not SHORTS_RE.search(text):
        #     if VERBOSE:
        #         print(f"[skip] {search_query} {vid}: no 'shorts' keyword in title/description")
        #     continue

        link = f"https://www.youtube.com/watch?v={vid}"
        items.append({"url": link, "title": title, "duration_seconds": dur})

    if VERBOSE:
        print(f"[found] {search_query}: {len(items)} items kept")
    return items

# ---- topics of interest ----
TOPICS = [
    "food review","street food","home cooking","recipe shorts","quick recipes","budget meals",
    # "fine dining plating","camp cooking","air fryer recipes","instant pot recipes","bbq grilling",
    # "deep fried snacks","baking dessert","pastry lamination","coffee brewing","milk tea boba",
    # "mocktail recipe","ramen","sushi","pho","bibimbap","birria tacos","ceviche","neapolitan pizza",
    # "smashburger","fried chicken","dumplings","dim sum","curry naan","biryani","pad thai","tom yum",
    # "sichuan noodles","thai street food","korean street food","japanese street food","mexican street food",
    # "indian street food","vietnamese street food","ethiopian injera","nigerian jollof","shawarma","falafel",
    # "gyro","poutine","pierogi","arepas","empanadas","vegan cooking","vegetarian recipes","gluten free baking",
    # "keto recipe","halal food","kosher food","breakfast pancakes","brunch ideas","lunch bowl","dinner ideas",
    # "late night snacks","chocolate dessert","cheesecake","ice cream","macarons","tiramisu","baklava",
    # "texas bbq","carolina bbq","gumbo","beignets","deep dish pizza","nyc bagels","poke bowl","pollo a la brasa",
    # "asado","turkish pide","manakish","laksa","chilli crab","nasi goreng","filipino adobo","taiwanese beef noodle",
    # "egg waffle","kottu roti","nihari","bhuna","momo","plov","moroccan tagine","bunny chow","jerk chicken",
    # "trinidad doubles","feijoada","cachapas","smoothie bowl","fresh juice","easy cocktails"
]

def main():
    max_results = 10
    out = {}
    total = 0
    for topic in TOPICS:
        kept = get_youtube_links(topic, max_results)
        out[topic] = kept
        total += len(kept)
        if VERBOSE:
            print(f"[write] {topic}: {len(kept)} items")

    outfile = "youtube_video_links.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[done] wrote {outfile} with {total} total items")

if __name__ == "__main__":
    main()
