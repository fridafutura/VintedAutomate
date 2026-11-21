"""Main orchestrator: runs continuously on the VPS, polling Vinted for likes,
messages and offers and reacting per the discount rules in config.py.

Intended to run as a systemd service (see README's deployment section), not
interactively. Logs everything to stdout (systemd/journald captures it) and
writes anything it can't answer itself to escalations.jsonl.

Known gap: when handle_incoming_offer decides to approve an offer, it sends
a reply message saying so, but VintedPlaywrightClient.update_price() (really
accepting/declining the structured offer in Vinted itself) is still
NotImplementedError - see that module's docstring for why. So right now the
seller still needs to confirm the offer by hand in Vinted after the message
goes out; this is logged loudly, not hidden.
"""

from __future__ import annotations

import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vintedautomate.claude_client import ClaudeClient
from vintedautomate.config import DEFAULT_RULES, DEFAULT_TIMING
from vintedautomate.likes import build_like_discount_message
from vintedautomate.message_handler import handle_incoming_message, handle_incoming_offer
from vintedautomate.models import Listing
from vintedautomate.vinted_playwright_client import VintedPlaywrightClient

SESSION_PATH = Path(__file__).resolve().parent.parent / "vinted_session.json"
ESCALATIONS_PATH = Path(__file__).resolve().parent.parent / "escalations.jsonl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("vintedautomate.run_agent")


def _in_quiet_hours() -> bool:
    hour = datetime.now().hour
    start, end = DEFAULT_TIMING.quiet_hours_start, DEFAULT_TIMING.quiet_hours_end
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # wraps past midnight


def _escalate(kind: str, listing_title: str, buyer_id: str, detail: str, reason: str) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "kind": kind,
        "listing_title": listing_title,
        "buyer_id": buyer_id,
        "detail": detail,
        "reason": reason,
    }
    with open(ESCALATIONS_PATH, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.warning("ESKALATION (%s) '%s' von %s: %s - %s", kind, listing_title, buyer_id, detail, reason)


def _reply_delay() -> None:
    time.sleep(random.uniform(DEFAULT_TIMING.reply_delay_min_seconds, DEFAULT_TIMING.reply_delay_max_seconds))


def _resolve_listing(client: VintedPlaywrightClient, title: str) -> Listing | None:
    listing = client.get_registered_listing(title)
    if listing is None:
        logger.warning(
            "'%s' nicht im lokalen Register gefunden - scan_my_listings() lief evtl. noch nicht "
            "oder der Titel stimmt nicht exakt überein.",
            title,
        )
    return listing


def run_one_cycle(client: VintedPlaywrightClient, claude: ClaudeClient) -> None:
    if not client.is_logged_in():
        logger.error(
            "Nicht eingeloggt - Session abgelaufen. Lauf bootstrap_login.py erneut "
            "auf deinem Rechner und kopier die neue vinted_session.json hierher."
        )
        return

    client.scan_my_listings()

    try:
        likes = client.get_new_likes()
    except NotImplementedError as e:
        logger.info("Like-Abfrage noch nicht verdrahtet: %s", e)
        likes = []

    for item_title, buyer_id in likes:
        listing = _resolve_listing(client, item_title)
        if listing is None:
            _escalate("like", item_title, buyer_id, "Like erkannt", "Kein Preis im Register gefunden")
            continue
        reply, decision = build_like_discount_message(listing, claude)
        logger.info("Like auf '%s' von %s -> %s", item_title, buyer_id, decision.reason)
        _reply_delay()
        client.send_message(listing.id, buyer_id, reply)

    try:
        messages = client.get_new_messages()
    except NotImplementedError as e:
        logger.info("Nachrichten-Abfrage noch nicht verdrahtet: %s", e)
        messages = []

    for message in messages:
        listing = _resolve_listing(client, message.listing_id)
        if listing is None:
            _escalate("message", message.listing_id, message.buyer_id, message.text, "Kein Preis im Register gefunden")
            continue
        result = handle_incoming_message(listing, message, claude)
        if result.escalate_to_seller:
            _escalate("message", message.listing_id, message.buyer_id, message.text, result.escalation_reason)
            continue
        _reply_delay()
        client.send_message(listing.id, message.buyer_id, result.auto_reply_text)

    try:
        offers = client.get_new_offers()
    except NotImplementedError as e:
        logger.info("Angebots-Abfrage noch nicht verdrahtet: %s", e)
        offers = []

    for offer in offers:
        listing = _resolve_listing(client, offer.listing_id)
        if listing is None:
            _escalate(
                "offer", offer.listing_id, offer.buyer_id,
                f"Angebot: {offer.offered_price_eur:.2f} €", "Kein Preis im Register gefunden",
            )
            continue
        decision_result = handle_incoming_offer(listing, offer, claude)
        if decision_result.escalate_to_seller:
            _escalate(
                "offer", offer.listing_id, offer.buyer_id,
                f"Angebot: {offer.offered_price_eur:.2f} €", decision_result.escalation_reason,
            )
            continue
        _reply_delay()
        client.send_message(listing.id, offer.buyer_id, decision_result.auto_reply_text)
        logger.warning(
            "Angebot zu '%s' von %s beantwortet, aber update_price() ist noch nicht verdrahtet - "
            "Preis/Angebot in Vinted muss noch von Hand bestätigt werden.",
            offer.listing_id, offer.buyer_id,
        )


def main() -> None:
    claude = ClaudeClient()

    while True:
        if _in_quiet_hours():
            logger.info("Ruhezeit - keine Aktionen, warte...")
            time.sleep(DEFAULT_TIMING.poll_interval_max_seconds)
            continue

        try:
            with VintedPlaywrightClient(SESSION_PATH, headless=True, rules=DEFAULT_RULES) as client:
                run_one_cycle(client, claude)
        except Exception:
            logger.exception("Fehler in diesem Durchlauf, versuche es beim nächsten Mal wieder")

        delay = random.uniform(
            DEFAULT_TIMING.poll_interval_min_seconds, DEFAULT_TIMING.poll_interval_max_seconds
        )
        logger.info("Nächster Durchlauf in %.0f Minuten", delay / 60)
        time.sleep(delay)


if __name__ == "__main__":
    main()
