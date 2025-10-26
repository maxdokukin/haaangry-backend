# app/main.py
from typing import List, Dict, Optional, Any
from pathlib import Path
import os
import json
import traceback
from urllib.parse import unquote, parse_qs

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


def _short(s: str, limit: int = 160) -> str:
    s = (s or "").replace("\n", "\\n")
    return s if len(s) <= limit else s[:limit] + "…"

@app.on_event("startup")
def startup():
    global RAW_ITEMS, DOWNLOAD_DIR

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


def _recipes_core(video_id: str, title_override: Optional[str] = None, desc_override: Optional[str] = None) -> RecipeLinksResult:
    print(f"[recipes:_core] video_id={video_id} title_override_set={bool(title_override)} desc_override_set={bool(desc_override)}")
    title = (title_override or "").strip()
    desc = (desc_override or "").strip()
    if not title and not desc:
        print("[recipes:_core] No overrides provided. Falling back to _lookup_title_desc.")
        meta = _lookup_title_desc(video_id)
        title = meta["title"].strip()
        desc = meta["description"].strip()
    else:
        print(f"[recipes:_core] Using overrides. title='{_short(title)}' desc_len={len(desc)}")

    prompt = _prompt_for_recipes(title, desc)
    rec_links_fetcher = ClaudeClient(
        json_schema="""[ {label: "Super delicios cake", "link": "https://..."}, ... ]"""
    )
    raw_text = rec_links_fetcher.ask_web_enforce_json(prompt)

    links = _parse_recipe_links_json(raw_text)
    q = title or desc or "N/A"

    print(f"[recipes:_core] built query text len={len(q)} links_count={len(links)}")
    result = RecipeLinksResult(video_id=video_id, query=q, links=links)
    print(f"[recipes:_core] returning RecipeLinksResult(video_id={result.video_id}, links={len(result.links)})")
    return result

# @app.get("/recipes", response_model=RecipeLinksResult)
# def recipes(video_id: str = Query(...), title: str | None = None, description: str | None = None) -> RecipeLinksResult:
#     return _recipes_core(video_id, title_override=title, desc_override=description)

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
