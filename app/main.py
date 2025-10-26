# app/main.py
from typing import List, Dict, Optional
from pathlib import Path
import json
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

# Claude client
try:
    from .src.Claude import ClaudeClient  # requires ANTHROPIC_API_KEY in env
except Exception:  # import-safe fallback
    ClaudeClient = None  # type: ignore

app = FastAPI(title="haaangry-demo-api", version="0.1.2")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# App state
RAW_ITEMS: List[dict] = []
DOWNLOAD_DIR: Path | None = None
CLAUDE: Optional["ClaudeClient"] = None  # type: ignore[name-defined]


@app.on_event("startup")
def startup():
    global RAW_ITEMS, DOWNLOAD_DIR, CLAUDE
    items, download_dir = data_loader.load_raw(config.FEED_JSON)
    RAW_ITEMS = items
    DOWNLOAD_DIR = config.DOWNLOAD_DIR or download_dir

    if DOWNLOAD_DIR and DOWNLOAD_DIR.exists():
        app.mount("/videos", StaticFiles(directory=str(DOWNLOAD_DIR)), name="videos")

    # Lazy Claude init; keep app running if missing key
    if ClaudeClient is not None:
        try:
            CLAUDE = ClaudeClient()
        except Exception:
            CLAUDE = None


@app.get("/feed", response_model=List[Video])
def feed(request: Request) -> List[Video]:
    base = str(request.base_url)
    return data_loader.build_feed(RAW_ITEMS, base_url=base, mounted_prefix="/videos", mounted_dir=DOWNLOAD_DIR)


@app.get("/order/options", response_model=OrderOptions)
def order_options(video_id: str = Query(...), title: str | None = None) -> OrderOptions:
    t = title
    if not t:
        for r in RAW_ITEMS:
            if str(r.get("id")) == video_id:
                t = r.get("title") or ""
                break
    return options_for(video_id, t or "")


# Compatibility for clients that mistakenly URL-encode the "?" into the path.
@app.get("/order/options{rest:path}", response_model=OrderOptions)
def order_options_compat(rest: str, title: str | None = None) -> OrderOptions:
    # rest could be like "%3Fvideo_id%3Dabc123" or "?video_id=abc123&title=Spicy%20Ramen"
    q = unquote(rest.lstrip("/"))
    if q.startswith("?"):
        q = q[1:]
    params = parse_qs(q)
    vid = (params.get("video_id") or [None])[0]
    title_param = (params.get("title") or [None])[0] or title
    if not vid:
        raise HTTPException(status_code=400, detail="video_id missing")
    return order_options(video_id=vid, title=title_param)


@app.post("/orders", response_model=Order)
def create_order(order: Order) -> Order:
    order.status = "confirmed"
    order.eta_minutes = 30
    return order


@app.post("/llm/text")
def llm_text(req: LLMTextReq):
    opts = options_for(req.recent_video_id or "demo", req.user_text)
    return {"intent": opts.intent, "top_restaurants": opts.top_restaurants}


@app.post("/llm/voice")
def llm_voice(req: LLMVoiceReq):
    opts = options_for(req.recent_video_id or "demo", req.transcript)
    return {"intent": opts.intent, "top_restaurants": opts.top_restaurants}


def _lookup_title_desc(video_id: str) -> Dict[str, str]:
    title, desc = "", ""
    for r in RAW_ITEMS:
        if str(r.get("id")) == video_id:
            title = r.get("title") or ""
            desc = r.get("description") or ""
            break
    return {"title": title, "description": desc}


def _prompt_for_recipes(title: str, description: str) -> str:
    # Ask Claude to search and return JSON links only.
    return (
        "You are an assistant that finds cooking recipes on the web.\n"
        f"Video title: {title or 'N/A'}\n"
        f"Video description: {description or 'N/A'}\n\n"
        "Task: Search the public web for 5–8 high-quality recipe pages that match the most likely dish.\n"
        "Prefer reputable food sites and original sources. Avoid spam and video-only pages.\n"
        "Return ONLY valid JSON with this schema:\n"
        '{\n  "links": [ {"title": "string", "url": "https://..."} ]\n}\n'
        "No markdown. No commentary. Ensure absolute HTTP(S) URLs."
    )


def _call_claude(prompt: str) -> Dict:
    if CLAUDE is None:
        return {"links": []}
    try:
        txt = CLAUDE.ask_with_web(prompt)
        data = json.loads(txt)
        if isinstance(data, dict) and isinstance(data.get("links"), list):
            # Normalize items
            clean = []
            for it in data["links"]:
                if isinstance(it, dict):
                    t = str(it.get("title") or "").strip()
                    u = str(it.get("url") or "").strip()
                    if t and u and u.startswith(("http://", "https://")):
                        clean.append({"title": t, "url": u})
            return {"links": clean}
        # If Claude returned a raw list
        if isinstance(data, list):
            clean = []
            for it in data:
                if isinstance(it, dict):
                    t = str(it.get("title") or "").strip()
                    u = str(it.get("url") or "").strip()
                    if t and u and u.startswith(("http://", "https://")):
                        clean.append({"title": t, "url": u})
            return {"links": clean}
        return {"links": []}
    except Exception:
        return {"links": []}


def _recipes_core(video_id: str, title_override: Optional[str] = None, desc_override: Optional[str] = None) -> RecipeLinksResult:
    title = (title_override or "").strip()
    desc = (desc_override or "").strip()
    if not title and not desc:
        meta = _lookup_title_desc(video_id)
        title = meta["title"].strip()
        desc = meta["description"].strip()

    prompt = _prompt_for_recipes(title, desc)
    payload = _call_claude(prompt)
    links = [Link(**it) for it in payload.get("links", []) if isinstance(it, dict)]
    # Build the query string we used for traceability
    q = title
    if desc:
        q = f"{q} — {desc}" if q else desc
    return RecipeLinksResult(video_id=video_id, query=q or "N/A", links=links)


@app.get("/recipes", response_model=RecipeLinksResult)
def recipes(
    video_id: str = Query(...),
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> RecipeLinksResult:
    return _recipes_core(video_id, title_override=title, desc_override=description)


# Compatibility for encoded query sent in the path, e.g. /recipes%3Fvideo_id%3Dabc&title=...
@app.get("/recipes{rest:path}", response_model=RecipeLinksResult)
def recipes_compat(rest: str) -> RecipeLinksResult:
    print('recipes_compat', rest)
    q = unquote(rest.lstrip("/"))
    if q.startswith("?"):
        q = q[1:]
    params = parse_qs(q)
    vid = (params.get("video_id") or [None])[0]
    title = (params.get("title") or [None])[0]
    description = (params.get("description") or [None])[0]
    if not vid:
        raise HTTPException(status_code=400, detail="video_id missing")
    return _recipes_core(vid, title_override=title, desc_override=description)


@app.get("/profile", response_model=Profile)
def profile() -> Profile:
    return Profile(**config.PROFILE)


@app.get("/orders/history")
def orders_history() -> Dict[str, list]:
    return {"orders": []}
