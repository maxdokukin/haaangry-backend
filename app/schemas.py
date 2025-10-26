# app/schemas.py
from typing import List, Optional
from pydantic import BaseModel

# ---- iOS-aligned models ----

class Video(BaseModel):
    id: str
    url: str
    thumb_url: Optional[str] = None
    title: str
    description: str
    tags: List[str]
    like_count: int
    comment_count: int

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
    tags: Optional[List[str]] = None

class OrderItem(BaseModel):
    menu_item_id: str
    name_snapshot: str
    price_cents_snapshot: int
    quantity: int

class Order(BaseModel):
    id: str
    user_id: str
    restaurant_id: str
    status: str
    items: List[OrderItem]
    subtotal_cents: int
    delivery_fee_cents: int
    total_cents: int
    eta_minutes: int

class OrderOptions(BaseModel):
    video_id: str
    intent: str
    top_restaurants: List[Restaurant]
    prefill: List[OrderItem]
    suggested_items: List[MenuItem]

# ---- New recipe search models ----

class Link(BaseModel):
    title: str
    url: str

class RecipeLinksResult(BaseModel):
    video_id: str
    query: str
    links: List[Link]

# ---- LLM request models ----

class LLMTextReq(BaseModel):
    user_text: str
    recent_video_id: Optional[str] = None

class LLMVoiceReq(BaseModel):
    transcript: str
    recent_video_id: Optional[str] = None

class Profile(BaseModel):
    user_id: str
    name: str
    credits_balance_cents: int
    default_address: dict

# ---- Recommendation flow models ----

class RestaurantBlock(BaseModel):
    restaurant_id: str
    restaurant_name: str
    menu_url: str
    items: List[MenuItem]
    avg_price_cents: int

class RecommendIn(BaseModel):
    video_id: str

class RecommendOut(BaseModel):
    recommendations: List[RestaurantBlock]

class ConfirmIn(BaseModel):
    restaurant_id: str
    item: OrderItem