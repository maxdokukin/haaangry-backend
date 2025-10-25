import json
from pathlib import Path
import yt_dlp

def main(
    input_json="youtube_video_links_enriched.json",
    output_json="youtube_video_links_enriched_downloaded.json",
    download_dir="downloads",
    fmt="bv*+ba/b"  # best video+audio, fallback to best single
):
    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    with open(input_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    ydl_opts = {
        "format": fmt,
        "merge_output_format": "mp4",
        "outtmpl": str(download_dir / "%(id)s.%(ext)s"),  # <downloads>/<id>.mp4
        "quiet": False,
        "noprogress": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for category, items in list(data.items()):
            if not isinstance(items, list):
                continue
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                url = item.get("url") or item.get("webpage_url")
                vid = item.get("id")
                if not url or not vid:
                    continue
                try:
                    ydl.download([url])
                    item["download_path"] = str((download_dir / f"{vid}.mp4").resolve())
                except Exception as e:
                    item["download_error"] = str(e)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
