# app/main.py
from typing import List, Dict, Optional
from pathlib import Path
import json
import os
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
    # noqa: E402
from . import data_loader
from .mock_data import options_for

# Claude client
try:
    from .src.Claude import ClaudeClient  # requires ANTHROPIC_API_KEY in env
except Exception as e:  # import-safe fallback
    print(f"[startup] Claude import failed: {e}")
    traceback.print_exc()
    ClaudeClient = None  # type: ignore

app = FastAPI(title="haaangry-demo-api", version="0.1.3")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# App state
RAW_ITEMS: List[dict] = []
DOWNLOAD_DIR: Path | None = None
CLAUDE: Optional["ClaudeClient"] = None  # type: ignore[name-defined]


def _short(s: str, limit: int = 160) -> str:
    s = (s or "").replace("\n", "\\n")
    return s if len(s) <= limit else s[:limit] + "…"


@app.on_event("startup")
def startup():
    global RAW_ITEMS, DOWNLOAD_DIR, CLAUDE

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

    # Lazy Claude init; keep app running if missing key
    if ClaudeClient is not None:
        try:
            key_present = bool(os.environ.get("ANTHROPIC_API_KEY"))
            print(f"[startup] ANTHROPIC_API_KEY present={key_present}")
            CLAUDE = ClaudeClient()
            # type: ignore[attr-defined]
            print(f"[startup] Claude initialized. model={getattr(CLAUDE, 'model', 'unknown')} max_tokens={getattr(CLAUDE, 'max_tokens', 'unknown')}")
        except Exception as e:
            print(f"[startup] Claude init failed: {e}")
            traceback.print_exc()
            CLAUDE = None
    else:
        print("[startup] ClaudeClient unavailable; skipping LLM initialization.")


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
    """
    New required LLM output format:
    A JSON array with EXACTLY 3 objects. No markdown. No commentary.
    Each object has:
      - DESCRIPTION: short text for the recipe link
      - LINK: absolute http(s) URL
    Example:
    [
      {"DESCRIPTION": "Classic spaghetti carbonara", "LINK": "https://example.com/a"},
      {"DESCRIPTION": "Serious Eats carbonara", "LINK": "https://example.com/b"},
      {"DESCRIPTION": "Bon Appétit carbonara", "LINK": "https://example.com/c"}
    ]
    """
    prompt = (
        "You are an assistant that finds cooking recipes on the web.\n"
        f"Video title: {title or 'N/A'}\n"
        f"Video description: {description or 'N/A'}\n\n"
        "Task: Search the public web for EXACTLY 3 high-quality recipe pages that match the most likely dish.\n"
        "Prefer reputable food sites and original sources. Avoid spam and video-only pages.\n"
        "Respond with JSON ONLY. No markdown. No commentary. Output must be an array of 3 objects with keys DESCRIPTION and LINK.\n"
        'Return format:\n'
        '[{"DESCRIPTION":"string","LINK":"https://..."}, {"DESCRIPTION":"string","LINK":"https://..."}, {"DESCRIPTION":"string","LINK":"https://..."}]\n'
        "Ensure absolute HTTP(S) URLs."
    )
    print(f"[recipes:_prompt_for_recipes] prompt_len={len(prompt)} preview='{_short(prompt, 200)}'")
    return prompt


def _call_claude(prompt: str) -> Dict:
    """
    Calls Claude and parses the new [{DESCRIPTION, LINK} * 3] JSON.
    Tolerates lower/upper case keys. Validates http(s) scheme. Trims to 3.
    Falls back to old shape if encountered.
    """
    if CLAUDE is None:
        print("[recipes:_call_claude] CLAUDE is None. Returning empty links.")
        return {"links": []}
    try:
        print(f"[recipes:_call_claude] calling Claude.ask_web_enforce_json prompt_len={len(prompt)} model={getattr(CLAUDE, 'model', 'unknown')}")

        txt = CLAUDE.ask_web_enforce_json(prompt)
        print(f"[recipes:_call_claude] raw_text_len={len(txt)} preview='{_short(txt, 200)}'")
        data = json.loads(txt)

        def _coerce_list_payload(obj) -> List[Dict[str, str]]:
            out: List[Dict[str, str]] = []
            if not isinstance(obj, list):
                return out
            for it in obj:
                if not isinstance(it, dict):
                    continue
                # Case-insensitive keys
                # Accept DESCRIPTION/description and LINK/link
                desc = it.get("DESCRIPTION") or it.get("description") or it.get("Description") or ""
                link = it.get("LINK") or it.get("link") or it.get("Url") or it.get("URL") or ""
                d = str(desc).strip()
                u = str(link).strip()
                if d and u and u.startswith(("http://", "https://")):
                    out.append({"title": d, "url": u})
            return out

        links: List[Dict[str, str]] = []

        # New format first
        links = _coerce_list_payload(data)

        # Fallback: old {"links":[{"title","url"}]} or list of {"title","url"}
        if not links:
            if isinstance(data, dict) and isinstance(data.get("links"), list):
                for it in data["links"]:
                    if isinstance(it, dict):
                        t = str(it.get("title") or "").strip()
                        u = str(it.get("url") or "").strip()
                        if t and u and u.startswith(("http://", "https://")):
                            links.append({"title": t, "url": u})
            elif isinstance(data, list):
                for it in data:
                    if isinstance(it, dict):
                        t = str(it.get("title") or "").strip()
                        u = str(it.get("url") or "").strip()
                        if t and u and u.startswith(("http://", "https://")):
                            links.append({"title": t, "url": u})

        # Enforce at most 3
        links = links[:3]
        print(f"[recipes:_call_claude] parsed links count={len(links)}")
        return {"links": links}
    except Exception as e:
        print(f"[recipes:_call_claude] EXCEPTION: {e}")
        traceback.print_exc()
        return {"links": []}


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
    payload = _call_claude(prompt)
    links = [Link(**it) for it in payload.get("links", []) if isinstance(it, dict)]
    q = title
    if desc:
        q = f"{q} — {desc}" if q else desc
    print(f"[recipes:_core] built query='{_short(q)}' links_count={len(links)}")
    result = RecipeLinksResult(video_id=video_id, query=q or "N/A", links=links)
    print(f"[recipes:_core] returning RecipeLinksResult(video_id={result.video_id}, links={len(result.links)})")
    return result


@app.get("/recipes", response_model=RecipeLinksResult)
def recipes(
    video_id: str = Query(...),
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> RecipeLinksResult:
    print(f"[/recipes] GET video_id={video_id} title_set={bool(title)} description_len={len(description or '')}")
    res = _recipes_core(video_id, title_override=title, desc_override=description)
    print(f"[/recipes] DONE links={len(res.links)}")
    return res


# Compatibility for encoded query sent in the path, e.g. /recipes%3Fvideo_id%3Dabc&title=...
@app.get("/recipes/{rest:path}", response_model=RecipeLinksResult)
def recipes_compat(rest: str) -> RecipeLinksResult:
    print(f"[/recipes compat] rest='{rest}'")
    q = unquote(rest.lstrip("/"))
    print(f"[/recipes compat] unquoted='{q}'")
    if q.startswith("?"):
        q = q[1:]
    params = parse_qs(q)
    vid = (params.get("video_id") or [None])[0]
    title = (params.get("title") or [None])[0]
    description = (params.get("description") or [None])[0]
    print(f"[/recipes compat] parsed video_id={vid} title_set={bool(title)} description_len={len(description or '')}")
    if not vid:
        print("[/recipes compat] ERROR video_id missing")
        raise HTTPException(status_code=400, detail="video_id missing")
    res = _recipes_core(vid, title_override=title, desc_override=description)
    print(f"[/recipes compat] DONE links={len(res.links)}")
    return res


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
from typing import Tuple
from pydantic import ValidationError
from . import schemas as SCH  # access newly added schemas without touching earlier import
from pathlib import Path as _Path

# Local restaurant catalog (loaded in a separate startup hook so we don't touch the existing one)
_REST_CATALOG: dict = {}
_REST_BY_ID: dict = {}

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

@app.on_event("startup")
def _startup_load_restaurants():
    global _REST_CATALOG, _REST_BY_ID
    _REST_CATALOG = _load_restaurants_json()
    _REST_BY_ID = {r.get("id"): r for r in _REST_CATALOG.get("restaurants", []) if isinstance(r, dict) and r.get("id")}
    print(f"[startup] Loaded restaurants.json count={len(_REST_BY_ID)}")

def _lookup_video_meta(video_id: str) -> Tuple[str, str]:
    # Reuse existing RAW_ITEMS
    meta = _lookup_title_desc(video_id)
    return meta.get("title", ""), meta.get("description", "")

def _claude_schema_for_choice() -> dict:
    # Compact schema for Claude → we convert to full objects later
    return {
        "type": "object",
        "properties": {
            "recommendations": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "restaurant_id": {"type": "string"},
                        "item_names": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 3,
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["restaurant_id", "item_names"]
                }
            }
        },
        "required": ["recommendations"]
    }

def _build_choice_prompt(title: str, description: str, catalog: dict) -> str:
    # Pass only what's needed: ids, names, menus with name+price+tags to keep prompt small
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
    # Use Claude JSON tool enforcement if available; we supply the schema at call time
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

def _fallback_simple_choice(title: str, description: str, catalog: dict) -> dict:
    # Token overlap fallback when LLM unavailable
    import re
    text = f"{title} {description}".lower()
    tokens = set(re.findall(r"[a-zA-Z]+", text))
    scores = []
    for r in catalog.get("restaurants", []):
        best = 0
        for m in r.get("menu", []):
            n = str(m.get("name","")).lower()
            overlap = len(tokens.intersection(set(n.split())))
            best = max(best, overlap)
        scores.append((best, r.get("id")))
    # pick top 3 ids by best overlap
    top_ids = [rid for _, rid in sorted(scores, key=lambda x: x[0], reverse=True)[:3] if rid]
    recs = []
    for rid in top_ids:
        r = _REST_BY_ID.get(rid)
        if not r:
            continue
        # choose the first 3 items as naive pick
        item_names = [m.get("name") for m in (r.get("menu") or [])][:3]
        recs.append({"restaurant_id": rid, "item_names": item_names})
    return {"recommendations": recs[:3]}

@app.post("/recommend", response_model=SCH.RecommendOut)
def recommend_api(body: SCH.RecommendIn):
    if not body.video_id:
        raise HTTPException(status_code=400, detail="video_id required")

    title, desc = _lookup_video_meta(body.video_id)
    print(f"[/recommend] video_id={body.video_id} title='{_short(title)}'")

    # Build prompt
    prompt = _build_choice_prompt(title, desc, _REST_CATALOG)

    # Prefer Claude JSON tool if available; otherwise use fallback
    raw_obj: dict
    if CLAUDE is not None and hasattr(CLAUDE, "client"):
        try:
            # Create a one-off client with JSON schema so we don't touch the first CLAUDE instance
            schema_client = None
            try:
                # Late import to avoid altering startup
                from .src.Claude import ClaudeClient as _CC  # type: ignore
                schema_client = _CC(json_schema=_claude_schema_for_choice(), temperature=0.0, max_tokens=800)
            except Exception as e:
                print(f"[/recommend] Could not init schema-bound ClaudeClient: {e}")

            if schema_client is not None and hasattr(schema_client, "ask_enforce_json"):
                txt = schema_client.ask_enforce_json(prompt)
            else:
                txt = CLAUDE.ask_enforce_json(prompt)  # fall back to existing client

            raw_obj = json.loads(txt or "{}")
            if not isinstance(raw_obj, dict) or "recommendations" not in raw_obj:
                raise ValueError("Claude returned non-object or missing 'recommendations'")
        except Exception as e:
            print(f"[/recommend] Claude path failed: {e}")
            raw_obj = _fallback_simple_choice(title, desc, _REST_CATALOG)
    else:
        print("[/recommend] CLAUDE unavailable, using fallback ranker")
        raw_obj = _fallback_simple_choice(title, desc, _REST_CATALOG)

    # Build typed response
    blocks: list[SCH.RestaurantBlock] = []
    for rec in raw_obj.get("recommendations", [])[:3]:
        rid = (rec or {}).get("restaurant_id")
        if rid not in _REST_BY_ID:
            continue
        item_names = list((rec or {}).get("item_names") or [])[:3]
        items, avg_cents = _items_to_menu_models(rid, item_names)
        # fill if Claude returned unknown names
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
            # recompute avg if needed
            if items:
                avg_cents = int(round(sum(i.price_cents for i in items) / len(items)))

        blocks.append(SCH.RestaurantBlock(
            restaurant_id=rid,
            restaurant_name=_REST_BY_ID[rid].get("name") or rid,
            items=items,
            avg_price_cents=avg_cents
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
