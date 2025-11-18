import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests
from datetime import datetime

from database import create_document, get_documents

app = FastAPI(title="Game Deals Aggregator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHEAPSHARK_BASE = "https://www.cheapshark.com/api/1.0"
EPIC_FREE_GAMES_URL = (
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
)


class WishlistPayload(BaseModel):
    user_id: str
    game_slug: str
    title: str
    cover_url: Optional[str] = None


class NotifyPayload(BaseModel):
    user_id: str
    title: str
    body: str
    deep_link: Optional[str] = None
    scheduled_at: Optional[datetime] = None


@app.get("/")
def read_root():
    return {"message": "Game Deals Aggregator Backend is running"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        from database import db

        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


@app.get("/api/deals")
def get_deals(
    title: Optional[str] = Query(None, description="Search title"),
    store_id: Optional[str] = Query(None, description="CheapShark storeID filter"),
    lower_price: Optional[float] = Query(None),
    upper_price: Optional[float] = Query(None),
    sort_by: Optional[str] = Query("DealRating", description="Title|Savings|Price|Metacritic|Reviews|Release|Store|recent") ,
    page_size: int = Query(20, ge=1, le=60),
):
    """
    Proxy to CheapShark deals with basic filters.
    https://apidocs.cheapshark.com/
    """
    params: Dict[str, Any] = {"pageSize": page_size, "sortBy": sort_by}
    if title:
        params["title"] = title
    if store_id:
        params["storeID"] = store_id
    if lower_price is not None:
        params["lowerPrice"] = lower_price
    if upper_price is not None:
        params["upperPrice"] = upper_price

    try:
        r = requests.get(f"{CHEAPSHARK_BASE}/deals", params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        return {"count": len(data), "items": data}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"CheapShark error: {e}")


@app.get("/api/games/search")
def search_games(
    title: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=60)
):
    """Search games via CheapShark quick search."""
    try:
        r = requests.get(f"{CHEAPSHARK_BASE}/games", params={"title": title, "limit": limit}, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"CheapShark error: {e}")


@app.get("/api/epic/free")
def epic_free_games(locale: str = "en-US", country: str = "US"):
    """Fetch weekly free Epic Games titles from Epic public feed."""
    try:
        r = requests.get(EPIC_FREE_GAMES_URL, params={"locale": locale, "country": country, "allowCountries": country}, timeout=15)
        r.raise_for_status()
        payload = r.json()
        data = payload.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
        # Normalize minimal fields
        items = []
        for e in data:
            title = e.get("title")
            id_ = e.get("id")
            product_slug = (e.get("productSlug") or "")
            key_images = e.get("keyImages", [])
            image = next((img.get("url") for img in key_images if img.get("type") in {"DieselStoreFrontWide", "OfferImageTall", "DieselGameBox"}), None)
            price = (e.get("price", {}).get("totalPrice", {}).get("fmtPrice", {}) or {})
            promotions = e.get("promotions")
            is_free = False
            if promotions:
                current = promotions.get("promotionalOffers") or []
                for offer in current:
                    for p in offer.get("promotionalOffers", []):
                        if p.get("discountSetting", {}).get("discountType") == "PERCENTAGE" and p.get("discountSetting", {}).get("discountPercentage") == 0:
                            is_free = True
            items.append({
                "store": "epic",
                "id": id_,
                "title": title,
                "image": image,
                "productSlug": product_slug,
                "isFreeNow": is_free,
                "price": price,
            })
        # Only return free now
        free_now = [i for i in items if i.get("isFreeNow")]
        return {"count": len(free_now), "items": free_now}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Epic feed error: {e}")


@app.post("/api/wishlist")
def add_wishlist(item: WishlistPayload):
    try:
        doc_id = create_document("wishlistitem", item.model_dump())
        return {"ok": True, "id": doc_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/wishlist")
def get_wishlist(user_id: str = Query(...)):
    try:
        docs = get_documents("wishlistitem", {"user_id": user_id})
        # Convert ObjectId to string if present
        for d in docs:
            if "_id" in d:
                d["_id"] = str(d["_id"])
        return {"count": len(docs), "items": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/notify/price-drop")
def queue_notification(payload: NotifyPayload):
    try:
        doc_id = create_document("notificationticket", payload.model_dump())
        return {"queued": True, "id": doc_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
