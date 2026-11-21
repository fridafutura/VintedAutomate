"""Real Vinted automation via Playwright, driving a persistent logged-in
browser session (created once by scripts/bootstrap_login.py).

Confidence levels, to be honest about what's actually been verified:

- `publish_listing`: selectors are grounded in real screenshots of the
  "Artikel verkaufen" form (Fotos/Titel/Beschreibung/Kategorie/Preis,
  "Entwurf speichern"/"Hochladen" buttons, category search box). Should
  work, but run it once with headless=False and watch before trusting it
  unattended - Vinted can still have changed something since the
  screenshots, or shown an A/B-tested variant.
- Everything else (reading likes/messages/offers, sending replies) is a
  NotImplementedError stub. I have not seen the seller-side inbox,
  notifications, or offer-acceptance screens - only a buyer's view of
  someone else's listing. Guessing selectors for screens I've never seen
  risks silently doing the wrong thing (e.g. messaging the wrong person).
  Send screenshots of: your inbox/conversation list, a conversation where
  a buyer sent a price offer, and any "X liked your item" notification -
  then these get implemented for real instead of stubbed.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .config import DEFAULT_RULES, DEFAULT_TIMING, AutomationTiming, BusinessRules
from .models import IncomingMessage, Listing, ListingFields

logger = logging.getLogger("vintedautomate.playwright_client")

SELL_URL = "https://www.vinted.de/items/new"


def _human_delay(min_seconds: float, max_seconds: float) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


class VintedPlaywrightClient:
    def __init__(
        self,
        session_path: str | Path,
        headless: bool = True,
        rules: BusinessRules = DEFAULT_RULES,
        timing: AutomationTiming = DEFAULT_TIMING,
    ) -> None:
        self.session_path = Path(session_path)
        if not self.session_path.exists():
            raise FileNotFoundError(
                f"No session file at {self.session_path}. Run scripts/bootstrap_login.py "
                "on your own computer first, then copy the resulting file here."
            )
        self.rules = rules
        self.timing = timing
        self._headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> "VintedPlaywrightClient":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context(
            storage_state=str(self.session_path), locale="de-DE"
        )
        return self

    def __exit__(self, *exc_info) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _page(self) -> Page:
        assert self._context is not None, "Use VintedPlaywrightClient as a context manager"
        return self._context.new_page()

    def is_logged_in(self) -> bool:
        page = self._page()
        try:
            page.goto("https://www.vinted.de/", wait_until="domcontentloaded")
            # Logged-out visitors get redirected to/offered a login/signup prompt;
            # a quick heuristic rather than a single brittle selector.
            logged_out_markers = page.get_by_text("Einloggen", exact=False)
            return logged_out_markers.count() == 0
        finally:
            page.close()

    def publish_listing(self, fields: ListingFields) -> Listing:
        page = self._page()
        try:
            page.goto(SELL_URL, wait_until="domcontentloaded")
            _human_delay(1, 3)

            # --- Fotos ---
            if fields.photo_paths:
                with page.expect_file_chooser() as fc_info:
                    page.get_by_text("Fotos hinzufügen").click()
                fc_info.value.set_files(fields.photo_paths)
                _human_delay(1, 3)

            # --- Titel ---
            page.get_by_placeholder("Teile Käufern mit, was du verkaufst").fill(fields.title)
            _human_delay(0.5, 1.5)

            # --- Beschreibung ---
            page.get_by_placeholder("Erzähle Käufern mehr darüber").fill(fields.description)
            _human_delay(0.5, 1.5)

            # --- Kategorie (search box inside the dropdown) ---
            page.get_by_text("Wähle eine Kategorie").click()
            _human_delay(0.3, 0.8)
            page.get_by_placeholder("Finde eine Kategorie").fill(fields.category_search_term)
            _human_delay(1, 2)
            # Take the first live suggestion Vinted offers for this search term,
            # rather than assuming any particular category tree.
            page.locator("[role='option'], li").first.click()
            _human_delay(0.5, 1.5)

            # --- Preis ---
            price_field = page.get_by_text("Preis").locator("xpath=following::input[1]")
            price_field.fill(f"{fields.price_eur:.2f}".replace(".", ","))
            _human_delay(0.5, 1.5)

            if self.rules.auto_publish_listings:
                page.get_by_role("button", name="Hochladen").click()
                status = "published"
            else:
                page.get_by_role("button", name="Entwurf speichern").click()
                status = "draft"

            _human_delay(1, 2)
            logger.info("Listing '%s' -> %s", fields.title, status)

            # Vinted assigns the real item id; without the post-submit page
            # confirmed, fall back to a locally-generated placeholder id.
            return Listing(id=f"pending-{int(time.time())}", fields=fields)
        finally:
            page.close()

    # --- Not yet wired up: see module docstring ---

    def get_new_likes(self) -> list[tuple[str, str]]:
        raise NotImplementedError(
            "Needs a screenshot of your Vinted notifications/likes view before this "
            "can be implemented safely."
        )

    def get_new_messages(self) -> list[IncomingMessage]:
        raise NotImplementedError(
            "Needs a screenshot of your Vinted inbox/conversation list before this "
            "can be implemented safely."
        )

    def send_message(self, listing_id: str, buyer_id: str, text: str) -> None:
        raise NotImplementedError(
            "Needs to know how to navigate to a specific conversation (depends on "
            "get_new_messages being wired up first)."
        )

    def update_price(self, listing_id: str, new_price_eur: float) -> None:
        raise NotImplementedError(
            "Needs a screenshot of the seller-side offer-acceptance UI before this "
            "can be implemented safely."
        )
