"""Discount decision engine.

Three policies the seller specified, all enforced here in code rather than
left to an LLM's judgment on each call:

1. Anyone who "likes" an item gets an automatic 10% discount offer.
2. Every listing can move within a discount band of up to 15% (e.g. for
   price drops over time or light haggling).
3. If a buyer explicitly pushes for more in a message, the agent may go up
   to 20% off on its own, without asking the seller first.

In every case, the price must never drop below the seller's absolute floor
(8 €). If a requested discount would cross the floor, it is capped at the
floor instead of being auto-escalated to the seller — the floor rule is the
seller's fixed policy, not a judgment call.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import BusinessRules, DEFAULT_RULES


@dataclass
class DiscountDecision:
    approved: bool
    offered_price_eur: float | None
    offered_rate: float | None  # actual effective rate after any floor clamp
    escalate: bool
    reason: str
    hit_price_floor: bool = False


def _clamp_to_floor(current_price_eur: float, target_price_eur: float, rules: BusinessRules) -> tuple[float, bool]:
    if target_price_eur < rules.min_price_eur:
        return rules.min_price_eur, True
    return round(target_price_eur, 2), False


def like_discount(current_price_eur: float, rules: BusinessRules = DEFAULT_RULES) -> DiscountDecision:
    """The automatic discount offered when someone likes/favorites an item."""

    raw_target = current_price_eur * (1 - rules.like_discount_rate)
    final_price, hit_floor = _clamp_to_floor(current_price_eur, raw_target, rules)
    effective_rate = 1 - (final_price / current_price_eur)

    reason = f"Automatischer Like-Rabatt von {rules.like_discount_rate:.0%}."
    if hit_floor:
        reason += f" Preisuntergrenze von {rules.min_price_eur:.2f} € angewendet."

    return DiscountDecision(
        approved=True,
        offered_price_eur=final_price,
        offered_rate=round(effective_rate, 4),
        escalate=False,
        reason=reason,
        hit_price_floor=hit_floor,
    )


def evaluate_discount_request(
    current_price_eur: float,
    rules: BusinessRules = DEFAULT_RULES,
    requested_rate: float | None = None,
    requested_price_eur: float | None = None,
) -> DiscountDecision:
    """Decide how to respond to a buyer explicitly asking for a discount.

    Pass either `requested_rate` (e.g. 0.25 for "25% off?") or
    `requested_price_eur` (e.g. "would you do 9€?") — not both.
    """

    if (requested_rate is None) == (requested_price_eur is None):
        raise ValueError("Pass exactly one of requested_rate or requested_price_eur")

    if requested_price_eur is not None:
        if requested_price_eur <= 0 or requested_price_eur >= current_price_eur:
            effective_requested_rate = 0.0
        else:
            effective_requested_rate = 1 - (requested_price_eur / current_price_eur)
    else:
        effective_requested_rate = max(0.0, requested_rate)

    if effective_requested_rate > rules.max_autonomous_discount_rate:
        return DiscountDecision(
            approved=False,
            offered_price_eur=None,
            offered_rate=None,
            escalate=True,
            reason=(
                f"Gewünschter Rabatt (~{effective_requested_rate:.0%}) liegt über der "
                f"Grenze von {rules.max_autonomous_discount_rate:.0%}, die ich ohne "
                "Rückfrage genehmigen darf."
            ),
        )

    raw_target = current_price_eur * (1 - effective_requested_rate)
    final_price, hit_floor = _clamp_to_floor(current_price_eur, raw_target, rules)
    effective_rate = 1 - (final_price / current_price_eur)

    reason = f"Rabattwunsch von ~{effective_requested_rate:.0%} genehmigt (innerhalb der {rules.max_autonomous_discount_rate:.0%}-Grenze)."
    if hit_floor:
        reason += f" Preisuntergrenze von {rules.min_price_eur:.2f} € angewendet, daher etwas weniger Rabatt als gewünscht."

    return DiscountDecision(
        approved=True,
        offered_price_eur=final_price,
        offered_rate=round(effective_rate, 4),
        escalate=False,
        reason=reason,
        hit_price_floor=hit_floor,
    )
