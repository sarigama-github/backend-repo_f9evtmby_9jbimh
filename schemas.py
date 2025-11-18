"""
Database Schemas for Game Deals Aggregator

Each Pydantic model corresponds to a MongoDB collection.
Collection name is the lowercase class name.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict
from datetime import datetime


class Game(BaseModel):
    """
    Collection: game
    A normalized game document across stores/platforms.
    """
    slug: str = Field(..., description="Stable identifier for the game (kebab-case title or store app id)")
    title: str
    cover_url: Optional[HttpUrl] = None
    screenshots: Optional[List[HttpUrl]] = None
    trailer_url: Optional[HttpUrl] = None
    description: Optional[str] = None
    platforms: Optional[List[str]] = None  # ["pc", "ps", "xbox", "switch"]
    genres: Optional[List[str]] = None
    developer: Optional[str] = None
    publisher: Optional[str] = None
    release_date: Optional[datetime] = None
    store_ids: Optional[Dict[str, str]] = Field(
        default=None,
        description="Mapping of store -> store-specific id (e.g., steam: appid)"
    )
    metacritic: Optional[int] = Field(default=None, ge=0, le=100)
    opencritic: Optional[int] = Field(default=None, ge=0, le=100)


class Deal(BaseModel):
    """
    Collection: deal
    A price/deal entry for a specific store.
    """
    game_slug: str
    store: str  # steam, epic, gog, ps, xbox, nintendo, etc.
    store_item_id: Optional[str] = None
    price: float
    original_price: Optional[float] = None
    discount_pct: Optional[int] = Field(default=None, ge=0, le=100)
    currency: str = "USD"
    url: Optional[HttpUrl] = None
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    region: Optional[str] = Field(default="US")


class WishlistItem(BaseModel):
    """
    Collection: wishlistitem
    Wishlist entry keyed by a lightweight user id (device id or auth user id).
    """
    user_id: str
    game_slug: str
    title: str
    cover_url: Optional[HttpUrl] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NotificationTicket(BaseModel):
    """
    Collection: notificationticket
    A queued notification for a user (for demonstration/testing). Actual
    delivery to APNs/FCM should be handled by a worker.
    """
    user_id: str
    title: str
    body: str
    deep_link: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    scheduled_at: Optional[datetime] = None
    delivered: bool = False
