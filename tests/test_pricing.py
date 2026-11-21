import pytest

from vintedautomate.config import BusinessRules
from vintedautomate.models import ItemCondition, PriceComp
from vintedautomate.pricing import suggest_price

RULES = BusinessRules()


def test_no_comps_falls_back_to_price_floor():
    suggestion = suggest_price([], target_condition="good", rules=RULES)
    assert suggestion.suggested_price_eur == RULES.min_price_eur
    assert suggestion.comps_used == 0


def test_price_derived_from_median_of_comps():
    comps = [
        PriceComp(price_eur=10.0, condition=ItemCondition.VERY_GOOD),
        PriceComp(price_eur=12.0, condition=ItemCondition.VERY_GOOD),
        PriceComp(price_eur=50.0, condition=ItemCondition.VERY_GOOD),  # outlier
    ]
    suggestion = suggest_price(comps, target_condition="very_good", rules=RULES)
    assert suggestion.suggested_price_eur == 12.0
    assert suggestion.comps_used == 3


def test_suggestion_never_below_price_floor():
    comps = [PriceComp(price_eur=3.0, condition=ItemCondition.GOOD)]
    suggestion = suggest_price(comps, target_condition="good", rules=RULES)
    assert suggestion.suggested_price_eur == RULES.min_price_eur


def test_condition_normalization_adjusts_price_upward_for_better_condition():
    comps = [PriceComp(price_eur=20.0, condition=ItemCondition.GOOD)]
    suggestion = suggest_price(comps, target_condition="new_with_tags", rules=RULES)
    assert suggestion.suggested_price_eur > 20.0
