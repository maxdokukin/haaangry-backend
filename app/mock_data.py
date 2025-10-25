from typing import List
from .schemas import Restaurant, MenuItem, OrderItem, OrderOptions

# Simple demo catalog
RESTAURANTS: List[Restaurant] = [
    Restaurant(id="r1", name="Ramen Cart",  delivery_eta_min=25, delivery_eta_max=40, delivery_fee_cents=199),
    Restaurant(id="r2", name="Taco Truck Co", delivery_eta_min=20, delivery_eta_max=35, delivery_fee_cents=299),
    Restaurant(id="r3", name="Sushi Bar",   delivery_eta_min=30, delivery_eta_max=50, delivery_fee_cents=399),
]

MENU: List[MenuItem] = [
    MenuItem(id="m1", restaurant_id="r1", name="Spicy Tonkotsu Ramen", description="Rich pork broth", price_cents=1399, tags=["ramen","spicy"]),
    MenuItem(id="m2", restaurant_id="r1", name="Gyoza (6pc)", description="Pork dumplings", price_cents=599, tags=["dumplings"]),
    MenuItem(id="m3", restaurant_id="r2", name="Birria Tacos", description="Crispy with consomé", price_cents=1299, tags=["taco","birria"]),
    MenuItem(id="m4", restaurant_id="r3", name="Salmon Nigiri (6)", description="Fresh cut", price_cents=1499, tags=["sushi"]),
    MenuItem(id="m5", restaurant_id="r2", name="Al Pastor Taco", description=None, price_cents=399, tags=["taco"]),
]

def _intent_from_text(text: str) -> str:
    t = text.lower()
    if "ramen" in t: return "Spicy Ramen"
    if "taco" in t or "birria" in t: return "Birria Tacos"
    if "sushi" in t or "nigiri" in t: return "Sushi"
    if "burger" in t or "mcdonald" in t or "qpc" in t: return "Cheeseburger"
    if "korean" in t: return "Korean Street Food"
    return "Street Food"

def options_for(video_id: str, title: str) -> OrderOptions:
    intent = _intent_from_text(title)
    # crude selection
    if "ramen" in intent.lower():
        top = [RESTAURANTS[0], RESTAURANTS[2], RESTAURANTS[1]]
        prefill = [OrderItem(menu_item_id="m1", name_snapshot="Spicy Tonkotsu Ramen", price_cents_snapshot=1399, quantity=1)]
        suggested = [m for m in MENU if m.id in ("m2","m4")]
    elif "taco" in intent.lower() or "birria" in intent.lower():
        top = [RESTAURANTS[1], RESTAURANTS[0], RESTAURANTS[2]]
        prefill = [OrderItem(menu_item_id="m3", name_snapshot="Birria Tacos", price_cents_snapshot=1299, quantity=1)]
        suggested = [m for m in MENU if m.id in ("m5","m2")]
    elif "sushi" in intent.lower():
        top = [RESTAURANTS[2], RESTAURANTS[0], RESTAURANTS[1]]
        prefill = [OrderItem(menu_item_id="m4", name_snapshot="Salmon Nigiri (6)", price_cents_snapshot=1499, quantity=1)]
        suggested = [m for m in MENU if m.id in ("m1","m2")]
    else:
        top = RESTAURANTS
        prefill = [OrderItem(menu_item_id="m5", name_snapshot="Al Pastor Taco", price_cents_snapshot=399, quantity=2)]
        suggested = [m for m in MENU if m.id in ("m1","m2","m4")]
    return OrderOptions(video_id=video_id, intent=intent, top_restaurants=top, prefill=prefill, suggested_items=suggested)
