# pip install -U yt-dlp
import yt_dlp
import json

VERBOSE = True  # set False to reduce logs

# ---- your function, same search logic (ytsearch{max_results}:{query}) ----
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

    video_links_and_lengths = []
    for entry in result.get('entries', []) or []:
        link = f"https://www.youtube.com/watch?v={entry['id']}"
        duration = entry.get('duration', 0)
        video_links_and_lengths.append((link, duration))

    if VERBOSE:
        print(f"[found] {search_query}: {len(video_links_and_lengths)} items")
    return video_links_and_lengths

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

# ---- iterate topics and write JSON: { topic: [links...] } ----
def main():
    max_results = 10
    out = {}
    for topic in TOPICS:
        vids = get_youtube_links(topic, max_results)
        links = [link for link, _dur in vids]
        out[topic] = links
        if VERBOSE:
            print(f"[write] {topic}: {len(links)} links")

    outfile = "youtube_video_links.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[done] wrote {outfile} with {sum(len(v) for v in out.values())} total links")

if __name__ == "__main__":
    main()
