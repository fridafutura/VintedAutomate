import pytest

from vintedautomate.config import BusinessRules
from vintedautomate.discounts import evaluate_discount_request, like_discount

RULES = BusinessRules()


def test_like_discount_applies_standard_rate():
    decision = like_discount(20.0, RULES)
    assert decision.approved
    assert decision.offered_price_eur == 18.0
    assert decision.offered_rate == pytest.approx(0.10)
    assert not decision.hit_price_floor


def test_like_discount_never_crosses_price_floor():
    decision = like_discount(8.50, RULES)
    assert decision.offered_price_eur == RULES.min_price_eur
    assert decision.hit_price_floor


def test_discount_request_within_autonomous_limit_is_approved():
    decision = evaluate_discount_request(30.0, RULES, requested_rate=0.20)
    assert decision.approved
    assert not decision.escalate
    assert decision.offered_price_eur == 24.0


def test_discount_request_above_autonomous_limit_escalates():
    decision = evaluate_discount_request(30.0, RULES, requested_rate=0.35)
    assert not decision.approved
    assert decision.escalate
    assert decision.offered_price_eur is None


def test_discount_request_by_absolute_price_is_converted_to_rate():
    # Asking for 9€ off a 10€ item is a 10% discount -> within limits.
    decision = evaluate_discount_request(10.0, RULES, requested_price_eur=9.0)
    assert decision.approved
    assert decision.offered_price_eur == 9.0


def test_absolute_price_request_never_crosses_floor_even_if_within_rate_limit():
    # 20% off 9€ would be 7.20€, below the 8€ floor -> clamp to floor.
    decision = evaluate_discount_request(9.0, RULES, requested_rate=0.20)
    assert decision.approved
    assert decision.offered_price_eur == RULES.min_price_eur
    assert decision.hit_price_floor


def test_exactly_at_autonomous_limit_is_approved_not_escalated():
    decision = evaluate_discount_request(100.0, RULES, requested_rate=RULES.max_autonomous_discount_rate)
    assert decision.approved
    assert not decision.escalate


def test_requesting_both_rate_and_price_is_rejected():
    with pytest.raises(ValueError):
        evaluate_discount_request(10.0, RULES, requested_rate=0.1, requested_price_eur=9.0)


def test_requesting_neither_rate_nor_price_is_rejected():
    with pytest.raises(ValueError):
        evaluate_discount_request(10.0, RULES)


def test_structured_offer_reuses_same_floor_and_cap_logic():
    # A Vinted "Verhandeln" offer is just requested_price_eur under the hood.
    low_offer = evaluate_discount_request(20.0, RULES, requested_price_eur=19.0)
    assert low_offer.approved
    assert low_offer.offered_price_eur == 19.0

    too_low_offer = evaluate_discount_request(20.0, RULES, requested_price_eur=5.0)
    assert too_low_offer.escalate
