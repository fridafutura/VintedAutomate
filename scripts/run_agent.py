"""Main orchestrator: runs continuously on the VPS, polling Vinted for likes
and messages and reacting per the discount rules in config.py.

Intended to run as a systemd service (see README's deployment section), not
interactively. Logs everything to stdout (systemd/journald captures it).

Known gap: get_new_likes/get_new_messages on VintedPlaywrightClient are not
wired up yet (see that module's docstring) - this loop runs safely without
them (logs once per cycle that they're pending) rather than crashing, so
it's fine to deploy now and extend once those are implemented. Once they
are, this is where build_like_discount_message/handle_incoming_message get
called, with anything they escalate written out for the seller to check.
"""

from __future__ import annotations

import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vintedautomate.claude_client import ClaudeClient
from vintedautomate.config import DEFAULT_RULES, DEFAULT_TIMING
from vintedautomate.vinted_playwright_client import VintedPlaywrightClient

SESSION_PATH = Path(__file__).resolve().parent.parent / "vinted_session.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("vintedautomate.run_agent")


def _in_quiet_hours() -> bool:
    hour = datetime.now().hour
    start, end = DEFAULT_TIMING.quiet_hours_start, DEFAULT_TIMING.quiet_hours_end
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # wraps past midnight


def run_one_cycle(client: VintedPlaywrightClient, claude: ClaudeClient) -> None:
    if not client.is_logged_in():
        logger.error(
            "Nicht eingeloggt - Session abgelaufen. Lauf bootstrap_login.py erneut "
            "auf deinem Rechner und kopier die neue vinted_session.json hierher."
        )
        return

    # NOTE: get_new_likes/get_new_messages/get_new_offers identify a listing
    # by its title (there's no local record of your active listings' current
    # prices to run the discount engine against yet). Until there's a small
    # "my listings" registry (populated when publish_listing runs, or by
    # reading your own profile's item list), this loop can only detect and
    # log these events - it can't yet compute a real discount or reply.
    # That registry is the next concrete gap to close.

    try:
        likes = client.get_new_likes()
    except NotImplementedError as e:
        logger.info("Like-Abfrage noch nicht verdrahtet: %s", e)
        likes = []

    for item_title, buyer_id in likes:
        logger.info("Like auf '%s' von %s - Rabatt-Nachricht folgt, sobald Preis bekannt ist", item_title, buyer_id)

    try:
        messages = client.get_new_messages()
    except NotImplementedError as e:
        logger.info("Nachrichten-Abfrage noch nicht verdrahtet: %s", e)
        messages = []

    for message in messages:
        logger.info("Neue Nachricht zu '%s' von %s: %r", message.listing_id, message.buyer_id, message.text)

    try:
        offers = client.get_new_offers()
    except NotImplementedError as e:
        logger.info("Angebots-Abfrage noch nicht verdrahtet: %s", e)
        offers = []

    for offer in offers:
        logger.info(
            "Neues Preisangebot zu '%s' von %s: %.2f €", offer.listing_id, offer.buyer_id, offer.offered_price_eur
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
