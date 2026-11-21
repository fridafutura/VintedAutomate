"""Core data types shared across the pricing, discount and messaging logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ItemCondition(str, Enum):
    NEW_WITH_TAGS = "new_with_tags"
    NEW_WITHOUT_TAGS = "new_without_tags"
    VERY_GOOD = "very_good"
    GOOD = "good"
    SATISFACTORY = "satisfactory"


@dataclass
class RawItemInput:
    """What the seller actually provides for a new item: photos + a few notes.

    Everything else (title, description, category, color, material, ...) is
    filled in by the listing generator.
    """

    photo_paths: list[str]
    notes: str  # free text: brand, size if known, flaws, anything else
    category_hint: str | None = None  # optional, e.g. "Pullover", "Sneaker"


@dataclass
class PriceComp:
    """A comparable listing used as pricing evidence."""

    price_eur: float
    condition: ItemCondition | None = None
    title: str | None = None
    source: str = "manual"  # "manual" (seller-supplied) vs. future automated sources


@dataclass
class PriceSuggestion:
    suggested_price_eur: float
    min_price_eur: float
    basis: str  # human-readable explanation of how the price was derived
    comps_used: int


@dataclass
class ListingFields:
    """All fields that go into a Vinted listing."""

    title: str
    description: str
    category: str
    brand: str | None
    size: str | None
    color: str
    condition: ItemCondition
    material: str | None
    price_eur: float
    flaws_disclosed: list[str] = field(default_factory=list)


@dataclass
class Listing:
    id: str
    fields: ListingFields
    created_at: datetime = field(default_factory=datetime.utcnow)
    like_count: int = 0
    notified_like_discount: bool = False


class MessageIntent(str, Enum):
    QUESTION = "question"
    DISCOUNT_REQUEST = "discount_request"
    OTHER = "other"


@dataclass
class IncomingMessage:
    listing_id: str
    buyer_id: str
    text: str
    received_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentDecision:
    """Result of the agent deciding what to do about an incoming message
    or a like event."""

    auto_reply_text: str | None
    discount_offered_rate: float | None
    escalate_to_seller: bool
    escalation_reason: str | None = None
