"""Demo: simulate a "like" (-> automatic discount offer) and a buyer message
(-> question answered, discount negotiated, or escalated), all against the
mock Vinted client. No real Vinted access involved.

Usage:
    ANTHROPIC_API_KEY=... python scripts/simulate_like_and_message_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vintedautomate.claude_client import ClaudeClient
from vintedautomate.likes import build_like_discount_message
from vintedautomate.message_handler import handle_incoming_message
from vintedautomate.models import IncomingMessage, ItemCondition, ListingFields
from vintedautomate.vinted_client import InMemoryMockVintedClient


def main() -> None:
    claude = ClaudeClient()
    mock_client = InMemoryMockVintedClient()

    fields = ListingFields(
        title="Nike Hoodie, Größe M",
        description=(
            "Nike Hoodie in Größe M, dunkelblau, Baumwolle/Polyester-Mix. "
            "Zustand sehr gut, kaum getragen, keine Flecken oder Löcher. "
            "Maße: Breite ca. 55cm, Länge ca. 68cm."
        ),
        category="Damen > Pullover & Strickjacken",
        brand="Nike",
        size="M",
        color="Dunkelblau",
        condition=ItemCondition.VERY_GOOD,
        material="Baumwolle/Polyester",
        price_eur=18.0,
        flaws_disclosed=[],
    )
    listing = mock_client.publish_listing(fields)

    print("--- Like-Event ---")
    message, decision = build_like_discount_message(listing, claude)
    print(f"Entscheidung: {decision.reason}")
    print(f"Nachricht an Käufer: {message}\n")

    print("--- Eingehende Nachricht: Frage ---")
    question = IncomingMessage(listing_id=listing.id, buyer_id="buyer-1", text="Ist das Material kratzig oder weich?")
    result = handle_incoming_message(listing, question, claude)
    if result.escalate_to_seller:
        print(f"ESKALATION an dich: {result.escalation_reason}")
    else:
        print(f"Auto-Antwort: {result.auto_reply_text}")

    print("\n--- Eingehende Nachricht: Rabattwunsch (hoch) ---")
    discount_msg = IncomingMessage(listing_id=listing.id, buyer_id="buyer-2", text="Würdest du auf 12€ runtergehen?")
    result = handle_incoming_message(listing, discount_msg, claude)
    if result.escalate_to_seller:
        print(f"ESKALATION an dich: {result.escalation_reason}")
    else:
        print(f"Auto-Antwort: {result.auto_reply_text} (Rabatt: {result.discount_offered_rate:.0%})")


if __name__ == "__main__":
    main()
