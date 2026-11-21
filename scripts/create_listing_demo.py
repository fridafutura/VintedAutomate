"""Demo: create a listing from photos + notes, against the mock Vinted client.

Usage:
    ANTHROPIC_API_KEY=... python scripts/create_listing_demo.py \\
        --notes "Nike Hoodie, Größe M, kaum getragen" \\
        photo1.jpg photo2.jpg
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vintedautomate.claude_client import ClaudeClient
from vintedautomate.listing_generator import generate_listing
from vintedautomate.models import PriceComp, RawItemInput
from vintedautomate.pricing import suggest_price
from vintedautomate.vinted_client import InMemoryMockVintedClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("photos", nargs="+", help="Pfade zu Fotos des Artikels")
    parser.add_argument("--notes", required=True, help="Grobe Notizen zum Artikel")
    parser.add_argument(
        "--comp",
        action="append",
        default=[],
        metavar="PRICE",
        help="Preis eines Vergleichsangebots in Euro, mehrfach verwendbar, z.B. --comp 12.0",
    )
    args = parser.parse_args()

    claude = ClaudeClient()
    comps = [PriceComp(price_eur=float(p)) for p in args.comp]

    raw = RawItemInput(photo_paths=args.photos, notes=args.notes)

    # Condition isn't known yet at pricing time, so a first pass uses "good"
    # as a neutral assumption; generate_listing will determine the real
    # condition from the photos.
    price_guess = suggest_price(comps, target_condition="good")

    fields = generate_listing(raw, price_guess, claude)

    mock_client = InMemoryMockVintedClient()
    listing = mock_client.publish_listing(fields)

    print(f"Listing erstellt (mock): {listing.id}\n")
    print(f"Titel: {fields.title}")
    print(f"Kategorie: {fields.category_top_level} / {fields.category_search_term}")
    print(f"Marke: {fields.brand} | Größe: {fields.size} | Farbe: {fields.color}")
    condition_label = fields.condition.value if fields.condition else "nicht angegeben"
    print(f"Zustand: {condition_label} | Material: {fields.material}")
    print(f"Preis: {fields.price_eur:.2f} € ({price_guess.basis})")
    print(f"Mängel: {fields.flaws_disclosed or 'keine erkannt'}")
    print(f"\nBeschreibung:\n{fields.description}")


if __name__ == "__main__":
    main()
