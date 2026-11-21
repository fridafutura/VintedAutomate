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


# Top-level Vinted categories, as seen in the "Artikel verkaufen" form's
# category picker. The list may not be exhaustive (the picker was scrolled),
# but this is real UI, not a guess - keep it in sync if Vinted changes it.
VINTED_TOP_LEVEL_CATEGORIES = [
    "Damen",
    "Herren",
    "Kinder",
    "Home",
    "Elektronik",
    "Bücher & andere Medien",
    "Hobby- & Sammlerartikel",
]


@dataclass
class ListingFields:
    """All fields that go into a Vinted listing.

    `category_top_level` is one of VINTED_TOP_LEVEL_CATEGORIES (the only part
    of the category tree worth hardcoding - it's small and stable).

    `category_search_term` is NOT a validated path through the rest of the
    tree. Vinted's own category picker has a live search box ("Finde eine
    Kategorie"), and the deeper tree is far too large and volatile to mirror
    here (confirmed: it's effectively endless once you go past the top
    level). Instead, this is the search phrase (e.g. "Pullover", "Sneaker")
    that the future automation layer would type into that search box and
    pick the best real suggestion from - so the actual category always
    comes from Vinted live, never from a stale local copy.

    brand/size/color/condition/material are shown in the real form only
    after a category is picked, and which of them appear depends on the
    category (clothing vs. books vs. electronics, ...). They stay optional
    here for that reason, not because they're unimportant for clothing.
    """

    title: str
    description: str
    category_top_level: str
    category_search_term: str
    price_eur: float
    photo_paths: list[str] = field(default_factory=list)
    brand: str | None = None
    size: str | None = None
    color: str | None = None
    condition: ItemCondition | None = None
    material: str | None = None
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
class IncomingOffer:
    """A structured price offer submitted through Vinted's own "Verhandeln"
    flow - a concrete number, not free text. Distinct from IncomingMessage:
    no intent classification needed, the amount is already explicit."""

    listing_id: str
    buyer_id: str
    offered_price_eur: float
    received_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentDecision:
    """Result of the agent deciding what to do about an incoming message
    or a like event."""

    auto_reply_text: str | None
    discount_offered_rate: float | None
    escalate_to_seller: bool
    escalation_reason: str | None = None
