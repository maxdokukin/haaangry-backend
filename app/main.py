from typing import List, Dict
from pathlib import Path

from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .schemas import Video, OrderOptions, Order, LLMTextReq, LLMVoiceReq, RecipeResult, TextRecipe, Profile
from . import config
from . import data_loader
from .mock_data import options_for

app = FastAPI(title="haaangry-demo-api", version="0.1.0")

# CORS not strictly required for iOS, harmless for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# App state
RAW_ITEMS: List[dict] = []
DOWNLOAD_DIR: Path | None = None

@app.on_event("startup")
def startup():
    global RAW_ITEMS, DOWNLOAD_DIR
    items, download_dir = data_loader.load_raw(config.FEED_JSON)
    RAW_ITEMS = items
    DOWNLOAD_DIR = config.DOWNLOAD_DIR or download_dir

    # Mount local MP4s for AVPlayer
    if DOWNLOAD_DIR and DOWNLOAD_DIR.exists():
        app.mount("/videos", StaticFiles(directory=str(DOWNLOAD_DIR)), name="videos")
    else:
        # No local files -> still run, but /feed will filter out entries without a playable file
        pass

@app.get("/feed", response_model=List[Video])
def feed(request: Request) -> List[Video]:
    base = str(request.base_url)
    return data_loader.build_feed(RAW_ITEMS, base_url=base, mounted_prefix="/videos", mounted_dir=DOWNLOAD_DIR)

@app.get("/order/options", response_model=OrderOptions)
def order_options(video_id: str = Query(...), title: str | None = None) -> OrderOptions:
    # Lookup title from RAW_ITEMS if not provided
    t = title
    if not t:
        for r in RAW_ITEMS:
            if str(r.get("id")) == video_id:
                t = r.get("title") or ""
                break
    return options_for(video_id, t or "")

@app.post("/orders", response_model=Order)
def create_order(order: Order) -> Order:
    # Confirm and set ETA ~30 min for demo
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

@app.get("/recipes", response_model=RecipeResult)
def recipes(video_id: str = Query(...)) -> RecipeResult:
    # Trivial static demo
    return RecipeResult(
        video_id=video_id,
        top_text_recipes=[
            TextRecipe(title="Quick Spicy Tonkotsu", steps=["Boil broth","Add aromatics","Cook noodles","Assemble bowl"]),
            TextRecipe(title="Weeknight Ramen Hack", steps=["Stock + tare","Noodles","Chili oil","Toppings"]),
            TextRecipe(title="Rich Pork Ramen", steps=["Long simmer","Noodles","Egg","Scallions"]),
        ],
        top_youtube=["https://youtu.be/ramen1","https://youtu.be/ramen2","https://youtu.be/ramen3"],
    )

@app.get("/profile", response_model=Profile)
def profile() -> Profile:
    return Profile(**config.PROFILE)

@app.get("/orders/history")
def orders_history() -> Dict[str, list]:
    return {"orders": []}
