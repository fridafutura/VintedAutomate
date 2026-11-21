"""Turn a few photos + rough notes into a complete, Vinted-ready listing.

The goal (per the seller's own instructions) is to make each listing as
complete as possible up front, so buyers have fewer reasons to ask
follow-up questions.
"""

from __future__ import annotations

from .claude_client import ClaudeClient
from .models import VINTED_TOP_LEVEL_CATEGORIES, ItemCondition, ListingFields, PriceSuggestion, RawItemInput

_SYSTEM_PROMPT = f"""\
Du hilfst dabei, einen Secondhand-Artikel für ein Vinted-Angebot zu beschreiben.
Du bekommst Fotos des Artikels und ein paar grobe Notizen des Verkäufers.

Fülle alle Felder so vollständig und präzise wie möglich aus, damit Käufer möglichst
wenig Nachfragen haben. Sei ehrlich bei Mängeln (Flecken, Abnutzung, fehlende Teile) -
nenne sie konkret, beschönige nichts. Wenn du dir bei etwas (z.B. Marke, Material)
nicht sicher bist, schreibe das vorsichtiger ("vermutlich", "ca.") statt es zu erfinden.

Für die Kategorie gib zwei Dinge an: die oberste Ebene (immer einer von:
{", ".join(VINTED_TOP_LEVEL_CATEGORIES)}) und einen kurzen, präzisen Suchbegriff
für die genaue Unterkategorie (z.B. "Pullover", "Sneaker", "Jeans") - dieser
Begriff wird später in Vinteds eigenes Kategorie-Suchfeld eingetippt, du musst
also keine exakte Kategorie-Baumstruktur kennen, nur den treffendsten Begriff.

Antworte NUR mit einem JSON-Objekt in diesem Format:
{{
  "title": "kurzer, präziser Titel",
  "description": "vollständige Beschreibung inkl. Zustand, Passform, Maße falls erkennbar, Mängel",
  "category_top_level": "z.B. 'Damen'",
  "category_search_term": "z.B. 'Pullover'",
  "brand": "Marke oder null, wenn nicht erkennbar oder nicht zutreffend",
  "size": "Größe oder null, wenn nicht erkennbar oder nicht zutreffend",
  "color": "Hauptfarbe oder null, wenn nicht zutreffend",
  "condition": "einer von: new_with_tags, new_without_tags, very_good, good, satisfactory, oder null wenn nicht zutreffend",
  "material": "Material oder null, wenn nicht erkennbar oder nicht zutreffend",
  "flaws_disclosed": ["Liste konkreter Mängel, leer wenn keine erkennbar"]
}}
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

    condition = None
    if data.get("condition"):
        try:
            condition = ItemCondition(data["condition"])
        except ValueError:
            condition = ItemCondition.GOOD

    category_top_level = data.get("category_top_level", "").strip()
    if category_top_level not in VINTED_TOP_LEVEL_CATEGORIES:
        # Model drifted from the known list; fall back to the closest-sounding
        # one rather than erroring, the seller reviews this anyway.
        category_top_level = category_top_level or VINTED_TOP_LEVEL_CATEGORIES[0]

    return ListingFields(
        title=data.get("title", "").strip(),
        description=data.get("description", "").strip(),
        category_top_level=category_top_level,
        category_search_term=data.get("category_search_term", "").strip(),
        price_eur=price.suggested_price_eur,
        brand=data.get("brand") or None,
        size=data.get("size") or None,
        color=(data.get("color") or None) and data["color"].strip(),
        condition=condition,
        material=data.get("material") or None,
        flaws_disclosed=list(data.get("flaws_disclosed") or []),
    )
