"""Interface the rest of the system uses to talk to Vinted.

No real implementation lives here yet - that's the deliberately deferred
decision (browser automation vs. something else, and where it runs). This
module exists so the pricing/discount/content logic can be built and tested
end-to-end against `InMemoryMockVintedClient` now, and later swapped for a
real implementation without touching any other module.
"""

from __future__ import annotations

from typing import Protocol

from .models import IncomingMessage, IncomingOffer, Listing, ListingFields


class VintedClient(Protocol):
    def publish_listing(self, fields: ListingFields) -> Listing: ...

    def get_new_likes(self) -> list[tuple[str, str]]:
        """Returns (listing_id, buyer_id) pairs for likes not yet handled."""
        ...

    def get_new_messages(self) -> list[IncomingMessage]: ...

    def get_new_offers(self) -> list[IncomingOffer]:
        """Structured "Verhandeln" price offers, distinct from free-text messages."""
        ...

    def send_message(self, listing_id: str, buyer_id: str, text: str) -> None: ...

    def update_price(self, listing_id: str, new_price_eur: float) -> None: ...


class InMemoryMockVintedClient:
    """A fake Vinted for local testing / demos. Keeps everything in memory,
    never makes a network call."""

    def __init__(self) -> None:
        self._listings: dict[str, Listing] = {}
        self._sent_messages: list[tuple[str, str, str]] = []
        self._pending_likes: list[tuple[str, str]] = []
        self._pending_messages: list[IncomingMessage] = []
        self._pending_offers: list[IncomingOffer] = []
        self._next_id = 1

    def publish_listing(self, fields: ListingFields) -> Listing:
        listing_id = f"mock-{self._next_id}"
        self._next_id += 1
        listing = Listing(id=listing_id, fields=fields)
        self._listings[listing_id] = listing
        return listing

    def simulate_like(self, listing_id: str, buyer_id: str) -> None:
        self._pending_likes.append((listing_id, buyer_id))

    def simulate_message(self, message: IncomingMessage) -> None:
        self._pending_messages.append(message)

    def simulate_offer(self, offer: IncomingOffer) -> None:
        self._pending_offers.append(offer)

    def get_new_likes(self) -> list[tuple[str, str]]:
        likes, self._pending_likes = self._pending_likes, []
        return likes

    def get_new_messages(self) -> list[IncomingMessage]:
        messages, self._pending_messages = self._pending_messages, []
        return messages

    def get_new_offers(self) -> list[IncomingOffer]:
        offers, self._pending_offers = self._pending_offers, []
        return offers

    def send_message(self, listing_id: str, buyer_id: str, text: str) -> None:
        self._sent_messages.append((listing_id, buyer_id, text))

    def update_price(self, listing_id: str, new_price_eur: float) -> None:
        self._listings[listing_id].fields.price_eur = new_price_eur

    @property
    def sent_messages(self) -> list[tuple[str, str, str]]:
        return list(self._sent_messages)
