# haaangry-backend — FastAPI MVP

TikTok-style food feed backend for the **haaangry** hackathon app. Serves a local video feed, mock ordering, lightweight recipe links, and LLM-assisted recommendations. iOS is “online-first, offline-safe.”

---

## Quick start

```bash
# Python 3.11 recommended
python -m venv .venv && source .venv/bin/activate

pip install -r requirements.txt

# Required for /recipes and /recommend
export ANTHROPIC_API_KEY="<your key>"

# Optional overrides
export FEED_JSON="./data/videos.json"        # video metadata + download_path entries
export DOWNLOAD_DIR="./data/downloads"       # where the .mp4 files live

# Run
uvicorn app.main:app --reload --port 8000
# API: http://127.0.0.1:8000
```

> iOS defaults to `http://127.0.0.1:8000`. CORS is open for local dev.

---

## Project layout

```
app/
  main.py            # FastAPI app + endpoints
  config.py          # FEED_JSON, DOWNLOAD_DIR, demo profile
  data_loader.py     # flattens videos.json and builds playable feed
  mock_data.py       # stub restaurants/menu for intents → options
  schemas.py         # Pydantic models shared with iOS
  src/ClaudeClient.py# Anthropic helper with JSON/web enforcement
data/
  downloads/         # local .mp4 files (served at /videos)
  videos.json        # enriched YouTube metadata + download_path
  restaurants.json   # demo catalog for /recommend
```

---

## Environment and tools

- Python 3.11, FastAPI, Uvicorn, Pydantic.
- `ANTHROPIC_API_KEY` required for `/recipes` and `/recommend` (Claude web tools used).
- CORS: `allow_origins=["*"]` for demo.
- Static serving: if `DOWNLOAD_DIR` resolves, it is mounted at `/videos`.

---

## Data model (server-side)

Minimal entities used by the API. All currency in **cents**.

- **users**: id, name, email, default_address_id, credits_balance_cents  
- **addresses**: id, user_id, line1/line2/city/state/zip, lat/lng  
- **videos**: id, url, thumb_url, title, description, tags[], like_count, comment_count  
- **restaurants**: id, name, logo_url, delivery_eta_min/max, delivery_fee_cents  
- **menu_items**: id, restaurant_id, name, description?, price_cents, image_url?, tags[]?  
- **orders**: id, user_id, restaurant_id, status, subtotal_cents, delivery_fee_cents, total_cents, eta_minutes, created_at  
- **order_items**: id, order_id, menu_item_id, name_snapshot, price_cents_snapshot, quantity  
- **video_intents**: video_id → normalized intent and primary_menu_item_id  
- **recipes_cache** (optional): video_id → top text links + top YouTube links

Snapshots preserve historical prices in `order_items`.

---

## How video feed works

- `data/videos.json` holds per-topic arrays of YouTube items. Each kept item must have a **download_path** pointing to a local `.mp4` in `data/downloads/`.
- On startup, `data_loader.load_raw` flattens all topics to a list and computes the common download dir. If the dir exists, FastAPI serves it at `/videos`, and `/feed` returns playable URLs like `http://127.0.0.1:8000/videos/<id>.mp4`.
- Items without a resolvable local file are skipped so AVPlayer never tries to stream a YouTube watch page.

---

## API surface

Base URL: `http://127.0.0.1:8000`

### GET `/feed` → `[Video]`
Returns playable feed items.
```json
[
  {
    "id": "pgbrAtWxPKc",
    "url": "http://127.0.0.1:8000/videos/pgbrAtWxPKc.mp4",
    "thumb_url": "...",
    "title": "Food Review less than $10",
    "description": "",
    "tags": [],
    "like_count": 274819,
    "comment_count": 1000
  }
]
```

### GET `/order/options?video_id={id}&title={optional}` → `OrderOptions`
Rule-based intent and options from `mock_data.py`.
```json
{
  "video_id":"pgbrAtWxPKc",
  "intent":"Spicy Ramen",
  "top_restaurants":[{"id":"r1","name":"Ramen Cart","delivery_eta_min":25,"delivery_eta_max":40,"delivery_fee_cents":199}],
  "prefill":[{"menu_item_id":"m1","name_snapshot":"Spicy Tonkotsu Ramen","price_cents_snapshot":1399,"quantity":1}],
  "suggested_items":[{"id":"m2","restaurant_id":"r1","name":"Gyoza (6pc)","price_cents":599,"tags":["dumplings"]}]
}
```

### POST `/orders` → `Order`
Confirms immediately for demo.
```json
{
  "id":"o1",
  "user_id":"u1",
  "restaurant_id":"r1",
  "status":"confirmed",
  "items":[{"menu_item_id":"m1","name_snapshot":"Spicy Tonkotsu Ramen","price_cents_snapshot":1399,"quantity":1}],
  "subtotal_cents":1399,
  "delivery_fee_cents":199,
  "total_cents":1598,
  "eta_minutes":30
}
```

### POST `/llm/text` and `/llm/voice` → intent + top restaurants
Input: `{ "user_text": "birria tacos", "recent_video_id": "..." }` or `{ "transcript": "..." }`.  
Output mirrors `/order/options` subset.

### GET `/recipes?video_id={id}` → `RecipeLinksResult`
Runs two Claude web searches with JSON-only prompts. Returns up to 3 article links and 3 YouTube links, labeled and flattened.

### GET `/profile` → `Profile`
Static demo profile from `config.PROFILE`.

### GET `/orders/history` → `{ "orders": [] }`
Empty for MVP.

### POST `/recommend` → `RecommendOut`
LLM picks **exactly 3 restaurants** from `data/restaurants.json` and **3 items** per restaurant, then server maps to `MenuItem` models and computes `avg_price_cents`.
```json
{
  "recommendations":[
    {
      "restaurant_id":"mcdonalds_e_santa_clara_sj",
      "restaurant_name":"McDonald's – 1299 E Santa Clara St",
      "menu_url":"https://...",
      "items":[{"id":"mcdonalds_e_santa_clara_sj::big-mac","restaurant_id":"mcdonalds_e_santa_clara_sj","name":"Big Mac","price_cents":649}],
      "avg_price_cents":649
    }
  ]
}
```

### POST `/confirm` → placeholder
Echoes the selection for UI flow demos.

---

## Contracts and error handling

- Payloads are small and explicit. Integers for money. Client computes totals and server verifies on `/orders`.
- On iOS error or timeout the app falls back to bundled fixtures; the backend returns 2xx with predictable shapes.
- `/order/options` also has a “compat” route that tolerates clients that URL-encoded the `?` into the path.

---

## LLM integration

- `src/ClaudeClient.py` wraps Anthropic with two helpers:
  - `ask_enforce_json(...)`: forces JSON tool output or brace-slices then minifies.
  - `ask_web_enforce_json(...)`: enables `web_search_20250305` and `web_fetch_20250910` with citations, then returns minified JSON.
- Used by `/recipes` and `/recommend`. If `ANTHROPIC_API_KEY` is missing these routes will error; other routes still work.

---

## Fixtures and data prep

1) Collect candidates:
```bash
python data/collect_topics.py     # writes youtube_video_links_enriched.json
```
2) Download media:
```bash
python data/download.py           # populates data/downloads and writes ..._downloaded.json
```
3) Create or point `videos.json` at items with `download_path` entries.  
4) Place the restaurant catalog in `data/restaurants.json`.

---

## Testing with curl

```bash
curl -s http://127.0.0.1:8000/feed | jq length
curl -s "http://127.0.0.1:8000/order/options?video_id=pgbrAtWxPKc" | jq .intent
curl -s -X POST http://127.0.0.1:8000/orders   -H 'content-type: application/json'   -d '{"id":"o1","user_id":"u1","restaurant_id":"r1","status":"created","items":[{"menu_item_id":"m1","name_snapshot":"Spicy Tonkotsu Ramen","price_cents_snapshot":1399,"quantity":1}],"subtotal_cents":1399,"delivery_fee_cents":199,"total_cents":1598,"eta_minutes":0}'
```

---

## Known limitations

- Menus, restaurants, delivery, and payments are mocked.
- No auth; single static profile.
- Speech recognition is client-side; transcripts are posted to the backend as text only.
- No persistent DB yet; swap to Postgres later.

---

## License

Hackathon demo only. No production guarantees.
