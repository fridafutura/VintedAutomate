"""Business rules for VintedAutomate.

These numbers encode the seller's actual policy. They are deliberately kept
in one place and as plain constants (not buried in prompts) so the price
floor and discount caps are enforced in code, not just "requested" from an
LLM.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BusinessRules:
    # Never sell below this price, no matter what discount logic computes.
    min_price_eur: float = 8.0

    # Discount automatically offered to someone who liked/favorited an item.
    like_discount_rate: float = 0.10

    # Upper bound of the "standard" discount band every listing is allowed
    # to move within (e.g. price drops over time, light haggling).
    standard_discount_cap_rate: float = 0.15

    # If a buyer explicitly asks for a bigger discount in a message, the
    # agent may go this far on its own, without asking the seller first.
    max_autonomous_discount_rate: float = 0.20

    def __post_init__(self) -> None:
        if self.min_price_eur <= 0:
            raise ValueError("min_price_eur must be positive")
        if not (0 <= self.like_discount_rate <= self.standard_discount_cap_rate):
            raise ValueError("like_discount_rate must be within [0, standard_discount_cap_rate]")
        if not (self.standard_discount_cap_rate <= self.max_autonomous_discount_rate):
            raise ValueError("standard_discount_cap_rate must not exceed max_autonomous_discount_rate")
        if not (0 <= self.max_autonomous_discount_rate < 1):
            raise ValueError("max_autonomous_discount_rate must be in [0, 1)")


DEFAULT_RULES = BusinessRules()

ANTHROPIC_MODEL = os.environ.get("VINTEDAUTOMATE_MODEL", "claude-sonnet-5-5")
