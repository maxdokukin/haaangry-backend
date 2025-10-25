from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID, uuid4

app = FastAPI(title="BiteSwipe API", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Models ----------
class Video(BaseModel):
    id: str
    url: str
    thumb_url: Optional[str] = None
    title: str
    description: str
    tags: List[str] = []
    like_count: int = 0
    comment_count: int = 0

class Restaurant(BaseModel):
    id: str
    name: str
    logo_url: Optional[str] = None
    delivery_eta_min: int
    delivery_eta_max: int
    delivery_fee_cents: int

class MenuItem(BaseModel):
    id: str
    restaurant_id: str
    name: str
    description: Optional[str] = None
    price_cents: int
    image_url: Optional[str] = None
    tags: List[str] = []

class OrderItem(BaseModel):
    menu_item_id: str
    name_snapshot: str
    price_cents_snapshot: int
    quantity: int = 1

class Order(BaseModel):
    id: str
    user_id: str
    restaurant_id: str
    status: str = "created"
    items: List[OrderItem]
    subtotal_cents: int
    delivery_fee_cents: int
    total_cents: int
    eta_minutes: int

class OrderOptions(BaseModel):
    video_id: str
    intent: str  # e.g., "Spicy Ramen"
    top_restaurants: List[Restaurant]
    prefill: List[OrderItem]  # the pre-chosen item(s)
    suggested_items: List[MenuItem]

class TextRecipe(BaseModel):
    title: str
    steps: List[str]

class RecipeResult(BaseModel):
    video_id: str
    top_text_recipes: List[TextRecipe]
    top_youtube: List[str]  # plain YouTube URLs

class LLMRequest(BaseModel):
    user_text: Optional[str] = None
    transcript: Optional[str] = None
    recent_video_id: Optional[str] = None

class LLMResponse(BaseModel):
    intent: str
    top_restaurants: List[Restaurant]

# ---------- Stub Data ----------
VIDEOS = [
    Video(
        id="v1",
        url="https://example.com/videos/ramen.mp4",
        thumb_url="https://example.com/thumbs/ramen.jpg",
        title="Street Ramen",
        description="Rich tonkotsu ramen with chili oil and scallions.",
        tags=["ramen","spicy","japanese"],
        like_count=1234, comment_count=92
    ),
    Video(
        id="v2",
        url="https://example.com/videos/tacos.mp4",
        title="Birria Tacos",
        description="Crispy birria tacos with consommé dip.",
        tags=["taco","birria","mexican"],
        like_count=980, comment_count=48
    ),
]

RAMEN_PLACE = Restaurant(
    id="r1", name="Ramen Cart", logo_url=None,
    delivery_eta_min=25, delivery_eta_max=40, delivery_fee_cents=199
)
TACO_TRUCK = Restaurant(
    id="r2", name="Taco Truck Co", logo_url=None,
    delivery_eta_min=20, delivery_eta_max=35, delivery_fee_cents=299
)
SUSHI_BAR = Restaurant(
    id="r3", name="Sushi Bar", logo_url=None,
    delivery_eta_min=30, delivery_eta_max=50, delivery_fee_cents=399
)

MENU = [
    MenuItem(id="m1", restaurant_id="r1", name="Spicy Tonkotsu Ramen",
             description="Pork broth, chili oil", price_cents=1399),
    MenuItem(id="m2", restaurant_id="r1", name="Gyoza (6pc)",
             description="Pork dumplings", price_cents=599),
    MenuItem(id="m3", restaurant_id="r2", name="Birria Tacos (3)",
             description="With consommé", price_cents=1299),
    MenuItem(id="m4", restaurant_id="r3", name="Salmon Nigiri (6)",
             description="Fresh cut", price_cents=1499),
]

# ---------- Endpoints ----------

@app.get("/feed", response_model=List[Video])
def feed(page: int = 1, page_size: int = 10):
    return VIDEOS

@app.get("/order/options", response_model=OrderOptions)
def order_options(video_id: str = Query(...)):
    if video_id == "v1":
        intent = "Spicy Ramen"
        top = [RAMEN_PLACE, SUSHI_BAR, TACO_TRUCK]
        prefill = [OrderItem(menu_item_id="m1", name_snapshot="Spicy Tonkotsu Ramen", price_cents_snapshot=1399)]
        suggested = [m for m in MENU if m.id in ("m2","m4")]
    else:
        intent = "Birria Tacos"
        top = [TACO_TRUCK, RAMEN_PLACE, SUSHI_BAR]
        prefill = [OrderItem(menu_item_id="m3", name_snapshot="Birria Tacos (3)", price_cents_snapshot=1299)]
        suggested = [m for m in MENU if m.id in ("m2","m4")]
    return OrderOptions(video_id=video_id, intent=intent, top_restaurants=top, prefill=prefill, suggested_items=suggested)

@app.post("/orders", response_model=Order)
def create_order(order: Order):
    # echo back with “confirmed” and simple ETA math
    order.status = "confirmed"
    order.id = str(uuid4())
    order.eta_minutes = 30
    return order

@app.post("/llm/text", response_model=LLMResponse)
def llm_text(req: LLMRequest):
    intent = "Spicy Ramen" if "ramen" in (req.user_text or "").lower() else "Birria Tacos"
    return LLMResponse(intent=intent, top_restaurants=[RAMEN_PLACE, TACO_TRUCK, SUSHI_BAR])

@app.post("/llm/voice", response_model=LLMResponse)
def llm_voice(req: LLMRequest):
    intent = "Spicy Ramen" if "ramen" in (req.transcript or "").lower() else "Birria Tacos"
    return LLMResponse(intent=intent, top_restaurants=[RAMEN_PLACE, TACO_TRUCK, SUSHI_BAR])

@app.get("/recipes", response_model=RecipeResult)
def recipes(video_id: str = Query(...)):
    if video_id == "v1":
        text = [
            TextRecipe(title="Quick Spicy Tonkotsu", steps=["Boil broth","Add aromatics","Cook noodles","Assemble bowl"]),
            TextRecipe(title="Weeknight Ramen Hack", steps=["Stock + tare","Noodles","Chili oil","Toppings"]),
            TextRecipe(title="Rich Pork Ramen", steps=["Broth long simmer","Noodles","Egg","Scallions"])
        ]
        yt = ["https://youtu.be/ramen1","https://youtu.be/ramen2","https://youtu.be/ramen3"]
    else:
        text = [
            TextRecipe(title="Birria Basics", steps=["Toast chiles","Braise beef","Shred & sear","Dip"]),
            TextRecipe(title="Crispy Birria Tacos", steps=["Consommé","Queso","Griddle","Serve"]),
            TextRecipe(title="Birria Express", steps=["Pressure cooker","Assemble","Dip"])
        ]
        yt = ["https://youtu.be/birria1","https://youtu.be/birria2","https://youtu.be/birria3"]
    return RecipeResult(video_id=video_id, top_text_recipes=text, top_youtube=yt)

@app.get("/profile")
def profile():
    return {"user_id":"u1","name":"Alex","credits_balance_cents":3000,
            "default_address":{"line1":"1 Market St","city":"SF","state":"CA","zip":"94105"}}

@app.get("/orders/history")
def order_history():
    return {"orders":[]}
