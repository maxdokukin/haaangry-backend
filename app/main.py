# app/main.py
from typing import List, Dict, Optional, Any
from pathlib import Path
import os
import json
import traceback
from urllib.parse import unquote, parse_qs
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple
from pydantic import ValidationError
from . import schemas as SCH  # access newly added schemas without touching earlier import
from pathlib import Path as _Path
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .schemas import (
    Video,
    OrderOptions,
    Order,
    LLMTextReq,
    LLMVoiceReq,
    Profile,
    RecipeLinksResult,
    Link,
)
from . import config
from . import data_loader
from .mock_data import options_for
from .src.ClaudeClient import ClaudeClient  # requires ANTHROPIC_API_KEY in env

app = FastAPI(title="haaangry-demo-api", version="0.1.3")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# App state
RAW_ITEMS: List[dict] = []
DOWNLOAD_DIR: Path | None = None
_REST_CATALOG: dict = {}
_REST_BY_ID: dict = {}

def _short(s: str, limit: int = 160) -> str:
    s = (s or "").replace("\n", "\\n")
    return s if len(s) <= limit else s[:limit] + "…"

@app.on_event("startup")
def startup():
    global RAW_ITEMS, DOWNLOAD_DIR
    global _REST_CATALOG, _REST_BY_ID
    _REST_CATALOG = _load_restaurants_json()
    _REST_BY_ID = {r.get("id"): r for r in _REST_CATALOG.get("restaurants", []) if isinstance(r, dict) and r.get("id")}
    print(f"[startup] Loaded restaurants.json count={len(_REST_BY_ID)}")

    print(f"[startup] API version={app.version}")
    print(f"[startup] FEED_JSON={config.FEED_JSON} exists={config.FEED_JSON.exists()}")
    if config.DOWNLOAD_DIR:
        print(f"[startup] DOWNLOAD_DIR override from env → {config.DOWNLOAD_DIR}")

    try:
        items, download_dir = data_loader.load_raw(config.FEED_JSON)
        RAW_ITEMS = items
        DOWNLOAD_DIR = config.DOWNLOAD_DIR or download_dir
        print(f"[startup] Loaded RAW_ITEMS count={len(RAW_ITEMS)}")
        print(f"[startup] Computed common download_dir={download_dir}")
    except Exception as e:
        print(f"[startup] Failed to load feed JSON: {e}")
        traceback.print_exc()
        RAW_ITEMS = []
        DOWNLOAD_DIR = None

    if DOWNLOAD_DIR and DOWNLOAD_DIR.exists():
        app.mount("/videos", StaticFiles(directory=str(DOWNLOAD_DIR)), name="videos")
        print(f"[startup] Mounted /videos -> {DOWNLOAD_DIR}")
    else:
        print(f"[startup] No video mount. DOWNLOAD_DIR={DOWNLOAD_DIR} exists={DOWNLOAD_DIR.exists() if DOWNLOAD_DIR else None}")

@app.get("/feed", response_model=List[Video])
def feed(request: Request) -> List[Video]:
    base = str(request.base_url)
    print(f"[/feed] base_url={base}")
    vids = data_loader.build_feed(RAW_ITEMS, base_url=base, mounted_prefix="/videos", mounted_dir=DOWNLOAD_DIR)
    print(f"[/feed] returning videos count={len(vids)}")
    return vids

@app.get("/order/options", response_model=OrderOptions)
def order_options(video_id: str = Query(...), title: str | None = None) -> OrderOptions:
    print(f"[/order/options] video_id={video_id} title_override={bool(title)}")
    t = title
    if not t:
        for r in RAW_ITEMS:
            if str(r.get("id")) == video_id:
                t = r.get("title") or ""
                break
        print(f"[/order/options] looked up title='{_short(t or '')}'")
    opts = options_for(video_id, t or "")
    print(f"[/order/options] intent='{opts.intent}' top_restaurants={len(opts.top_restaurants)} prefill={len(opts.prefill)} suggested={len(opts.suggested_items)}")
    return opts


# Compatibility for clients that mistakenly URL-encode the "?" into the path.
@app.get("/order/options/{rest:path}", response_model=OrderOptions)
def order_options_compat(rest: str, title: str | None = None) -> OrderOptions:
    print(f"[/order/options compat] rest='{rest}' title_override={bool(title)}")
    q = unquote(rest.lstrip("/"))
    if q.startswith("?"):
        q = q[1:]
    params = parse_qs(q)
    vid = (params.get("video_id") or [None])[0]
    title_param = (params.get("title") or [None])[0] or title
    print(f"[/order/options compat] parsed video_id={vid} title_param='{_short(title_param or '')}'")
    if not vid:
        print("[/order/options compat] ERROR video_id missing")
        raise HTTPException(status_code=400, detail="video_id missing")
    return order_options(video_id=vid, title=title_param)


@app.post("/orders", response_model=Order)
def create_order(order: Order) -> Order:
    print(f"[/orders] create_order items={len(order.items)} subtotal={order.subtotal_cents} fee={order.delivery_fee_cents} total={order.total_cents}")
    order.status = "confirmed"
    order.eta_minutes = 30
    print(f"[/orders] confirmed eta_minutes={order.eta_minutes}")
    return order


@app.post("/llm/text")
def llm_text(req: LLMTextReq):
    print(f"[/llm/text] user_text='{_short(req.user_text)}' recent_video_id={req.recent_video_id}")
    opts = options_for(req.recent_video_id or "demo", req.user_text)
    print(f"[/llm/text] intent='{opts.intent}' top_restaurants={len(opts.top_restaurants)}")
    return {"intent": opts.intent, "top_restaurants": opts.top_restaurants}


@app.post("/llm/voice")
def llm_voice(req: LLMVoiceReq):
    print(f"[/llm/voice] transcript_len={len(req.transcript or '')} recent_video_id={req.recent_video_id}")
    opts = options_for(req.recent_video_id or "demo", req.transcript)
    print(f"[/llm/voice] intent='{opts.intent}' top_restaurants={len(opts.top_restaurants)}")
    return {"intent": opts.intent, "top_restaurants": opts.top_restaurants}


def _lookup_title_desc(video_id: str) -> Dict[str, str]:
    print(f"[recipes:_lookup_title_desc] video_id={video_id}")
    title, desc = "", ""
    for r in RAW_ITEMS:
        if str(r.get("id")) == video_id:
            title = r.get("title") or ""
            desc = r.get("description") or ""
            break
    print(f"[recipes:_lookup_title_desc] title='{_short(title)}' desc_len={len(desc)}")
    return {"title": title, "description": desc}


def _prompt_for_recipes(title: str, description: str) -> str:
    prompt = (
        "Find up to three high-quality cooking recipe pages for the most likely dish.\n"
        f"Video title: {title or 'N/A'}\n"
        f"Video description: {description or 'N/A'}\n"
        "Prefer reputable food sites and original sources.\n"
        "Return JSON only as an array (max 3). Each item is an object with keys:\n"
        "  - title: string\n"
        "  - link: string URL\n"
    )
    print(f"[recipes:_prompt_for_recipes] prompt_len={len(prompt)} preview='{_short(prompt, 200)}'")
    return prompt


def _prompt_for_recipes_videos(title: str, description: str) -> str:
    prompt = (
        "Find up to three high-quality cooking recipe youtube videos for the most likely dish.\n"
        f"Root Video title: {title or 'N/A'}\n"
        f"Root Video description: {description or 'N/A'}\n"
        "Prefer reputable authors.\n"
        "Return JSON only as an array (max 3). Each item is an object with keys:\n"
        "  - title: string\n"
        "  - link: string URL\n"
    )
    print(f"[recipes:_prompt_for_recipes_videos] prompt_len={len(prompt)} preview='{_short(prompt, 200)}'")
    return prompt


def _parse_recipe_links_json(s: str) -> List[Link]:
    try:
        obj = json.loads(s)
    except Exception:
        return []
    if not isinstance(obj, list):
        return []
    links: List[Link] = []
    for it in obj[:3]:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()
        # schema uses "link"; accept "url" as fallback
        url = str(it.get("link") or it.get("url") or "").strip()
        if title and url:
            links.append(Link(title=title, url=url))
    return links


def _recipes_core(
    video_id: str,
    title_override: Optional[str] = None,
    desc_override: Optional[str] = None,
) -> RecipeLinksResult:
    print(f"[recipes:_core] video_id={video_id} title_override_set={bool(title_override)} desc_override_set={bool(desc_override)}")

    title = (title_override or "").strip()
    description = (desc_override or "").strip()

    if not title and not description:
        print("[recipes:_core] No overrides provided. Falling back to _lookup_title_desc.")
        meta = _lookup_title_desc(video_id)
        title = meta["title"].strip()
        description = meta["description"].strip()
    else:
        print(f"[recipes:_core] Using overrides. title='{_short(title)}' desc_len={len(description)}")

    articles_prompt = _prompt_for_recipes(title, description)
    videos_prompt = _prompt_for_recipes_videos(title, description)

    articles_client = ClaudeClient(
        json_schema='[{"title": "Example", "link": "https://..."}]'
    )
    videos_client = ClaudeClient(
        json_schema='[{"title": "Example", "link": "https://youtube.com/..."}]'
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_articles = pool.submit(articles_client.ask_web_enforce_json, articles_prompt)
        fut_videos = pool.submit(videos_client.ask_web_enforce_json, videos_prompt)
        raw_articles = fut_articles.result()
        raw_videos = fut_videos.result()

    article_links = _parse_recipe_links_json(raw_articles)  # List[Link]
    video_links = _parse_recipe_links_json(raw_videos)      # List[Link]

    # Flatten and tag. Keep original order: all articles first, then videos.
    flattened_links = (
        [{"title": "Read: " + it.title, "url": it.url, "kind": "article"} for it in article_links] +
        [{"title": "Watch: " + it.title, "url": it.url, "kind": "video"} for it in video_links]
    )

    query_text = title or description or "N/A"
    print(f"[recipes:_core] built query text len={len(query_text)} articles_count={len(article_links)} videos_count={len(video_links)} total={len(flattened_links)}")

    result = RecipeLinksResult(video_id=video_id, query=query_text, links=flattened_links)
    print(f"[recipes:_core] returning RecipeLinksResult(video_id={result.video_id}, links={len(result.links)})")
    print(f"[recipes:_core] SENT TO FRONT END", result)

    return result



@app.get("/recipes/{rest:path}", response_model=RecipeLinksResult)
def recipes_compat(rest: str, request: Request) -> RecipeLinksResult:
    q = unquote(rest.lstrip("/"))
    if q.startswith("?"):
        q = q[1:]
    params = parse_qs(q)
    vid = (params.get("video_id") or [None])[0]
    title = (params.get("title") or [None])[0]
    description = (params.get("description") or [None])[0]

    if not vid:
        qp = request.query_params
        vid = qp.get("video_id")
        title = title or qp.get("title")
        description = description or qp.get("description")

    if not vid:
        raise HTTPException(status_code=400, detail="video_id missing")
    output = _recipes_core(vid, title_override=title, desc_override=description)
    print("SENT TO FRONT END: ", output)
    return output


@app.get("/profile", response_model=Profile)
def profile() -> Profile:
    print("[/profile] returning static profile")
    return Profile(**config.PROFILE)


@app.get("/orders/history")
def orders_history() -> Dict[str, list]:
    print("[/orders/history] returning empty list")
    return {"orders": []}


# =========================
# == Recommendation flow ==
# =========================
def _slug(s: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in (s or "")).strip("-")

def _load_restaurants_json() -> dict:
    root = _Path(__file__).resolve().parents[1]
    p = root / "data" / "restaurants.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "restaurants" not in data:
            raise ValueError("restaurants.json missing 'restaurants' key")
        return data
    except Exception as e:
        print(f"[recommendation] Failed to load restaurants.json: {e}")
        return {"restaurants": []}

def _lookup_video_meta(video_id: str) -> Tuple[str, str]:
    # Reuse existing RAW_ITEMS
    meta = _lookup_title_desc(video_id)
    return meta.get("title", ""), meta.get("description", "")

def _build_choice_prompt(title: str, description: str, catalog: dict) -> str:
    minimal_catalog = {
        "restaurants": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "menu": [
                    {"name": m.get("name"), "price": m.get("price"), "tags": m.get("tags", [])}
                    for m in (r.get("menu") or []) if isinstance(m, dict)
                ],
            }
            for r in (catalog.get("restaurants") or []) if isinstance(r, dict)
        ]
    }
    SYSTEM = (
        "You pick restaurants and items from a provided catalog. "
        "Goal: choose EXACTLY 3 restaurants most relevant to the video, and for each choose EXACTLY 3 item names "
        "from that restaurant's menu that best match the video's content. "
        "Return STRICT JSON using the provided tool schema. No prose."
    )
    user = (
        f"VIDEO_TITLE: {title or 'N/A'}\n"
        f"VIDEO_DESCRIPTION: {description or 'N/A'}\n\n"
        f"CATALOG:\n{json.dumps(minimal_catalog, ensure_ascii=False)}"
    )
    return f"{SYSTEM}\n\n{user}"

def _items_to_menu_models(restaurant_id: str, item_names: list[str]) -> Tuple[list[SCH.MenuItem], int]:
    r = _REST_BY_ID.get(restaurant_id) or {}
    menu = r.get("menu") or []
    name_map = {str(m.get("name")).strip().lower(): m for m in menu if isinstance(m, dict)}
    out: list[SCH.MenuItem] = []
    cents_list: list[int] = []

    for nm in item_names:
        key = str(nm or "").strip().lower()
        m = name_map.get(key)
        if not m:
            continue
        price = m.get("price")
        price_cents = int(round(float(price) * 100)) if isinstance(price, (int, float, str)) and str(price) else 0
        item_id = f"{restaurant_id}::{_slug(m.get('name',''))}"
        out.append(SCH.MenuItem(
            id=item_id,
            restaurant_id=restaurant_id,
            name=m.get("name") or "",
            description=None,
            price_cents=price_cents,
            image_url=None,
            tags=m.get("tags") or None
        ))
        cents_list.append(price_cents)

    avg_cents = int(round(sum(cents_list) / len(cents_list))) if cents_list else 0
    return out, avg_cents

@app.post("/recommend", response_model=SCH.RecommendOut)
def recommend_api(body: SCH.RecommendIn):
    if not body.video_id:
        raise HTTPException(status_code=400, detail="video_id required")

    title, desc = _lookup_video_meta(body.video_id)
    print(f"[/recommend] video_id={body.video_id} title='{_short(title)}'")

    prompt = _build_choice_prompt(title, desc, _REST_CATALOG)

    # Enforce a top-level OBJECT with .restaurants[], each having id and items[]
    restaurant_agent = ClaudeClient(
        json_schema=(
            '{"type":"object","properties":{"restaurants":{"type":"array","items":'
            '{"type":"object","properties":{"id":{"type":"string"},"items":{"type":"array","items":{"type":"string"}}},'
            '"required":["id"]}}},"required":["restaurants"]}'
        )
    )

    txt = restaurant_agent.ask_enforce_json(prompt)
    try:
        data = json.loads(txt or "{}")
    except json.JSONDecodeError:
        data = {}

    # Accept several shapes: object with restaurants[], or a bare list, or [{"restaurants":[...]}]
    if isinstance(data, dict):
        restaurants = data.get("restaurants") or []
    elif isinstance(data, list):
        if data and isinstance(data[0], dict) and "restaurants" in data[0]:
            restaurants = data[0].get("restaurants") or []
        else:
            restaurants = data  # assume a bare list of recs
    else:
        restaurants = []

    print("raw_obj, ", {"restaurants": restaurants})

    blocks: list[SCH.RestaurantBlock] = []
    for rec in (restaurants or [])[:3]:
        if not isinstance(rec, dict):
            continue
        rid = rec.get("id")
        if not rid or rid not in _REST_BY_ID:
            continue

        # Accept either "items" or legacy "item_names"
        item_names = list(rec.get("items") or rec.get("item_names") or [])[:3]

        items, avg_cents = _items_to_menu_models(rid, item_names)

        if len(items) < 3:
            r = _REST_BY_ID[rid]
            existing = {it.name for it in items}
            for m in (r.get("menu") or []):
                if len(items) >= 3:
                    break
                n = m.get("name")
                if not n or n in existing:
                    continue
                extra_items, _ = _items_to_menu_models(rid, [n])
                if extra_items:
                    items.append(extra_items[0])
                    existing.add(n)
            if items:
                avg_cents = int(round(sum(i.price_cents for i in items) / len(items)))

        blocks.append(SCH.RestaurantBlock(
            restaurant_id=rid,
            restaurant_name=_REST_BY_ID[rid].get("name") or rid,
            menu_url=_REST_BY_ID[rid].get("website") or "",
            items=items,
            avg_price_cents=avg_cents or 0
        ))

    try:
        out = SCH.RecommendOut(recommendations=blocks)
    except ValidationError as ve:
        print(f"[/recommend] Validation error: {ve}")
        raise HTTPException(status_code=502, detail="Recommendation validation failed")

    print(f"[/recommend] returning {len(out.recommendations)} restaurants")
    return out


@app.post("/confirm")
def confirm_api(body: SCH.ConfirmIn):
    # Placeholder confirmation endpoint
    print(f"[/confirm] restaurant_id={body.restaurant_id} items={len(body.item.name_snapshot) if hasattr(body, 'item') else 1}")
    return {
        "status": "ok",
        "message": "Order confirmation placeholder",
        "selection": {
            "restaurant_id": body.restaurant_id,
            "item": body.item.model_dump()
        }
    }
