"""Turn a few photos + rough notes into a complete, Vinted-ready listing.

The goal (per the seller's own instructions) is to make each listing as
complete as possible up front, so buyers have fewer reasons to ask
follow-up questions.
"""

from __future__ import annotations

from .claude_client import ClaudeClient
from .models import ItemCondition, ListingFields, PriceSuggestion, RawItemInput

_SYSTEM_PROMPT = """\
Du hilfst dabei, ein Secondhand-Kleidungsstück für ein Vinted-Angebot zu beschreiben.
Du bekommst Fotos des Artikels und ein paar grobe Notizen des Verkäufers.

Fülle alle Felder so vollständig und präzise wie möglich aus, damit Käufer möglichst
wenig Nachfragen haben. Sei ehrlich bei Mängeln (Flecken, Abnutzung, fehlende Teile) -
nenne sie konkret, beschönige nichts. Wenn du dir bei etwas (z.B. Marke, Material)
nicht sicher bist, schreibe das vorsichtiger ("vermutlich", "ca.") statt es zu erfinden.

Antworte NUR mit einem JSON-Objekt in diesem Format:
{
  "title": "kurzer, präziser Titel",
  "description": "vollständige Beschreibung inkl. Zustand, Passform, Maße falls erkennbar, Mängel",
  "category": "z.B. 'Damen > Pullover'",
  "brand": "Marke oder null, wenn nicht erkennbar",
  "size": "Größe oder null, wenn nicht erkennbar",
  "color": "Hauptfarbe",
  "condition": "einer von: new_with_tags, new_without_tags, very_good, good, satisfactory",
  "material": "Material oder null, wenn nicht erkennbar",
  "flaws_disclosed": ["Liste konkreter Mängel, leer wenn keine erkennbar"]
}
"""


def generate_listing(
    raw: RawItemInput,
    price: PriceSuggestion,
    claude: ClaudeClient,
) -> ListingFields:
    user_text = (
        f"Notizen des Verkäufers: {raw.notes}\n"
        + (f"Kategorie-Hinweis: {raw.category_hint}\n" if raw.category_hint else "")
        + f"Vorgeschlagener Preis: {price.suggested_price_eur:.2f} € "
        f"(Begründung: {price.basis})"
    )

    data = claude.structured_request(
        system=_SYSTEM_PROMPT,
        user_text=user_text,
        photo_paths=raw.photo_paths,
    )

    try:
        condition = ItemCondition(data["condition"])
    except (KeyError, ValueError):
        condition = ItemCondition.GOOD

    return ListingFields(
        title=data.get("title", "").strip(),
        description=data.get("description", "").strip(),
        category=data.get("category", "").strip(),
        brand=data.get("brand") or None,
        size=data.get("size") or None,
        color=data.get("color", "").strip(),
        condition=condition,
        material=data.get("material") or None,
        price_eur=price.suggested_price_eur,
        flaws_disclosed=list(data.get("flaws_disclosed") or []),
    )
