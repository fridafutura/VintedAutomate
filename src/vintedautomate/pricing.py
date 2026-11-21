"""Price suggestion from comparable listings.

Deliberately source-agnostic: `comps` can come from the seller typing in a
few links/screenshots today, or from an automated lookup later. This module
never talks to Vinted directly.
"""

from __future__ import annotations

import statistics

from .config import BusinessRules, DEFAULT_RULES
from .models import PriceComp, PriceSuggestion

# How much condition differs from "very_good" shifts a comp's price before
# it's used as evidence, so a "good"-condition comp doesn't drag down the
# price of a "new_with_tags" item and vice versa.
_CONDITION_ADJUSTMENT = {
    "new_with_tags": 1.15,
    "new_without_tags": 1.08,
    "very_good": 1.0,
    "good": 0.9,
    "satisfactory": 0.75,
}


def suggest_price(
    comps: list[PriceComp],
    target_condition: str,
    rules: BusinessRules = DEFAULT_RULES,
) -> PriceSuggestion:
    """Suggest a price from comparable listings, normalized to the target
    item's condition, and never below the seller's price floor."""

    if not comps:
        return PriceSuggestion(
            suggested_price_eur=rules.min_price_eur,
            min_price_eur=rules.min_price_eur,
            basis="Keine Vergleichsangebote vorhanden – Preisuntergrenze verwendet.",
            comps_used=0,
        )

    target_factor = _CONDITION_ADJUSTMENT.get(target_condition, 1.0)
    normalized = []
    for comp in comps:
        comp_condition = comp.condition.value if comp.condition else "very_good"
        comp_factor = _CONDITION_ADJUSTMENT.get(comp_condition, 1.0)
        normalized.append(comp.price_eur * (target_factor / comp_factor))

    # Median is more robust against one outlier listing than a mean.
    raw_suggestion = statistics.median(normalized)
    final_price = max(rules.min_price_eur, round(raw_suggestion, 2))

    basis = (
        f"Median aus {len(comps)} Vergleichsangebot(en), "
        f"zustandsbereinigt auf '{target_condition}': {raw_suggestion:.2f} €."
    )
    if final_price != round(raw_suggestion, 2):
        basis += f" Preisuntergrenze von {rules.min_price_eur:.2f} € angewendet."

    return PriceSuggestion(
        suggested_price_eur=final_price,
        min_price_eur=rules.min_price_eur,
        basis=basis,
        comps_used=len(comps),
    )
