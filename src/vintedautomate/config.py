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

    # Publishing a listing is a one-way, public action. By default the
    # automation fills in everything but only saves it as a draft, so the
    # seller gets one final look before it goes live. Flip this once the
    # generated listings have proven reliable enough to trust fully.
    auto_publish_listings: bool = False

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


@dataclass(frozen=True)
class AutomationTiming:
    """Pacing for the real Vinted automation layer. Deliberately human-scale,
    not "as fast as possible" - see README on account-ban risk."""

    poll_interval_min_seconds: int = 10 * 60
    poll_interval_max_seconds: int = 30 * 60

    # Before sending any single message/offer-response, wait a random delay
    # in this range, so replies don't look instantaneous.
    reply_delay_min_seconds: int = 45
    reply_delay_max_seconds: int = 20 * 60

    # Hard stop: never run automated actions in this local hour range
    # (keeps activity inside plausible "a person is awake" hours).
    quiet_hours_start: int = 23
    quiet_hours_end: int = 7


DEFAULT_TIMING = AutomationTiming()
