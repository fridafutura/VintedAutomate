"""Reaction to a buyer liking/favoriting a listing: offer the standard
automatic discount, phrased as a short outgoing message."""

from __future__ import annotations

from .claude_client import ClaudeClient
from .config import BusinessRules, DEFAULT_RULES
from .discounts import DiscountDecision, like_discount
from .models import Listing

_PHRASE_LIKE_SYSTEM_PROMPT = """\
Formuliere eine kurze, freundliche Vinted-Erstnachricht auf Deutsch an jemanden,
der einen Artikel geliked/favorisiert hat. Biete genau den angegebenen reduzierten
Preis an, keine andere Zahl. Kurz, locker, keine Anrede/Signatur, nur der Text.
"""


def build_like_discount_message(listing: Listing, claude: ClaudeClient, rules: BusinessRules = DEFAULT_RULES) -> tuple[str, DiscountDecision]:
    fields = listing.fields
    decision = like_discount(fields.price_eur, rules)

    reply = claude.text_request(
        system=_PHRASE_LIKE_SYSTEM_PROMPT,
        user_text=(
            f"Artikel: {fields.title}\n"
            f"Regulärer Preis: {fields.price_eur:.2f} €\n"
            f"Reduzierter Preis: {decision.offered_price_eur:.2f} € "
            f"(ca. {decision.offered_rate:.0%} Rabatt)"
        ),
    )
    return reply, decision
