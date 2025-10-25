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

class TextRecipe(BaseModel):
    title: str
    steps: List[str]

class RecipeResult(BaseModel):
    video_id: str
    top_text_recipes: List[TextRecipe]
    top_youtube: List[str]

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
