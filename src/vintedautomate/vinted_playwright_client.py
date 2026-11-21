"""Real Vinted automation via Playwright, driving a persistent logged-in
browser session (created once by scripts/bootstrap_login.py).

Confidence levels, to be honest about what's actually been verified:

- `publish_listing`: selectors are grounded in real screenshots of the
  "Artikel verkaufen" form (Fotos/Titel/Beschreibung/Kategorie/Preis,
  "Entwurf speichern"/"Hochladen" buttons, category search box). Should
  work, but run it once with headless=False and watch before trusting it
  unattended - Vinted can still have changed something since the
  screenshots, or shown an A/B-tested variant.
- `get_new_messages`/`get_new_offers`/`send_message`: grounded in real
  screenshots of the seller's own Inbox (conversation list with
  preview text, message bubbles - own messages right/dark, buyer's
  left/light with avatar - and a price offer rendered inline as a bubble
  with the new price next to a struck-through old price). The exact CSS
  selectors are still an educated guess (built from visible text/structure,
  not page source), so run once with headless=False and watch before
  trusting it unattended. The official "Vinted" system/marketing account
  that also appears in the inbox is filtered out.
- `get_new_likes`/`update_price`: still NotImplementedError. No "X liked
  your item" notification has been seen yet (unclear if Vinted even
  surfaces that to sellers, vs. only a heart-count on the item itself -
  worth confirming). No accept/decline affordance on a pending incoming
  offer has been seen either (the offers shown so far were old/resolved
  ones) - a screenshot of an *active, unanswered* offer would unblock this.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .config import DEFAULT_RULES, DEFAULT_TIMING, AutomationTiming, BusinessRules
from .models import IncomingMessage, IncomingOffer, Listing, ListingFields

logger = logging.getLogger("vintedautomate.playwright_client")

SELL_URL = "https://www.vinted.de/items/new"
INBOX_URL = "https://www.vinted.de/inbox"  # best guess, verify live

_PRICE_RE = re.compile(r"(\d+[.,]\d{2})\s*€")

_SYSTEM_ACCOUNT_USERNAMES = {"Vinted"}


def _human_delay(min_seconds: float, max_seconds: float) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def _parse_offer_bubble(text: str) -> float | None:
    """A structured "Verhandeln" offer renders inline as a bubble with the
    new price next to a struck-through old price (e.g. "37,00 € 40,00 €").
    Two € amounts in one bubble is the heuristic for "this is an offer, not
    a free-text message"."""
    amounts = _PRICE_RE.findall(text)
    if len(amounts) >= 2:
        return float(amounts[0].replace(",", "."))
    return None


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
        self._inbox_cache: tuple[list[IncomingMessage], list[IncomingOffer]] | None = None

    def __enter__(self) -> "VintedPlaywrightClient":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context(
            storage_state=str(self.session_path), locale="de-DE"
        )
        self._inbox_cache = None
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

    # --- Local dedup state (so re-running a poll cycle doesn't re-handle
    # the same like/message/offer) ---

    def _load_json_state(self, path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _save_json_state(self, path: Path, state: dict) -> None:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    # --- Likes ("favorisiert"): confirmed via the notification bell, whose
    # entries read "{buyer} hat deinen Artikel {item} favorisiert." ---

    _LIKE_RE = re.compile(r"(.+?) hat deinen Artikel (.+?) favorisiert")

    def get_new_likes(self) -> list[tuple[str, str]]:
        likes_state_path = self.session_path.parent / "likes_state.json"
        page = self._page()
        try:
            page.goto("https://www.vinted.de/", wait_until="domcontentloaded")
            _human_delay(1, 2)

            # Best-effort: the bell icon's accessible name isn't confirmed from
            # page source, only its look in a screenshot - verify live.
            opened = False
            for name in ["Benachrichtigungen", "Notifications"]:
                bell = page.get_by_role("button", name=name)
                if bell.count():
                    bell.first.click()
                    opened = True
                    break
            if not opened:
                logger.warning(
                    "Benachrichtigungs-Glocke nicht gefunden - Selektor in "
                    "get_new_likes() muss gegen die echte Seite geprüft werden."
                )
                return []
            _human_delay(0.5, 1.5)

            state = self._load_json_state(likes_state_path)
            new_likes: list[tuple[str, str]] = []

            rows = page.get_by_text("favorisiert", exact=False).all_inner_texts()
            for raw_text in rows:
                match = self._LIKE_RE.search(raw_text.replace("\n", " "))
                if not match:
                    continue
                buyer, item_title = match.group(1).strip(), match.group(2).strip()
                key = f"{buyer}::{item_title}"
                if state.get(key):
                    continue
                state[key] = True
                new_likes.append((item_title, buyer))

            self._save_json_state(likes_state_path, state)
            return new_likes
        finally:
            page.close()

    # --- Inbox (messages + structured offers): confirmed via real
    # screenshots of the seller's own Inbox. ---

    def _scan_inbox(self) -> tuple[list[IncomingMessage], list[IncomingOffer]]:
        inbox_state_path = self.session_path.parent / "inbox_state.json"
        page = self._page()
        messages: list[IncomingMessage] = []
        offers: list[IncomingOffer] = []
        try:
            page.goto(INBOX_URL, wait_until="domcontentloaded")
            _human_delay(1, 2)

            # Best-effort: conversation rows are links whose href contains
            # "/inbox/" - a reasonable guess from URL conventions, not
            # confirmed from page source. Verify live.
            conversation_links = page.locator("a[href*='/inbox/']")
            state = self._load_json_state(inbox_state_path)

            for i in range(conversation_links.count()):
                link = conversation_links.nth(i)
                lines = [l.strip() for l in link.inner_text().split("\n") if l.strip()]
                if not lines:
                    continue
                username = lines[0]
                if username in _SYSTEM_ACCOUNT_USERNAMES:
                    continue  # Vinted's own marketing account, not a buyer

                preview = lines[-1] if len(lines) > 1 else ""
                if state.get(username) == preview:
                    continue  # nothing new in this conversation since last check

                href = link.get_attribute("href")
                conv_page = self._page()
                try:
                    conv_page.goto(f"https://www.vinted.de{href}", wait_until="domcontentloaded")
                    _human_delay(1, 2)

                    item_title = username
                    heading = conv_page.locator("h1, h2").first
                    if heading.count():
                        item_title = heading.inner_text().strip() or username

                    offered_price = _parse_offer_bubble(preview)
                    if offered_price is not None:
                        offers.append(IncomingOffer(
                            listing_id=item_title, buyer_id=username, offered_price_eur=offered_price
                        ))
                    else:
                        messages.append(IncomingMessage(
                            listing_id=item_title, buyer_id=username, text=preview
                        ))
                finally:
                    conv_page.close()

                state[username] = preview

            self._save_json_state(inbox_state_path, state)
        finally:
            page.close()

        return messages, offers

    def _ensure_inbox_scanned(self) -> tuple[list[IncomingMessage], list[IncomingOffer]]:
        if self._inbox_cache is None:
            self._inbox_cache = self._scan_inbox()
        return self._inbox_cache

    def get_new_messages(self) -> list[IncomingMessage]:
        messages, _ = self._ensure_inbox_scanned()
        return messages

    def get_new_offers(self) -> list[IncomingOffer]:
        _, offers = self._ensure_inbox_scanned()
        return offers

    def send_message(self, listing_id: str, buyer_id: str, text: str) -> None:
        page = self._page()
        try:
            page.goto(INBOX_URL, wait_until="domcontentloaded")
            _human_delay(1, 2)

            conversation_links = page.locator("a[href*='/inbox/']")
            target = conversation_links.filter(has_text=buyer_id).first
            if not target.count():
                raise RuntimeError(f"Konversation mit '{buyer_id}' nicht im Posteingang gefunden")
            target.click()
            _human_delay(1, 2)

            message_box = page.get_by_placeholder("Schreibe hier deine Nachricht")
            message_box.click()
            message_box.type(text, delay=random.uniform(30, 90))
            _human_delay(0.5, 1.5)

            # Best-effort: the send button's accessible name isn't confirmed -
            # it may just be an icon. Fall back to Enter, which chat UIs
            # commonly submit on.
            sent = False
            for name in ["Senden", "Send", "Nachricht senden"]:
                btn = page.get_by_role("button", name=name)
                if btn.count():
                    btn.first.click()
                    sent = True
                    break
            if not sent:
                message_box.press("Enter")

            _human_delay(0.5, 1.5)
            logger.info("Nachricht an %s gesendet", buyer_id)
        finally:
            page.close()

    def update_price(self, listing_id: str, new_price_eur: float) -> None:
        raise NotImplementedError(
            "Needs a screenshot of the seller-side offer-acceptance UI (an "
            "active, unanswered incoming offer) before this can be implemented "
            "safely - the offers seen so far were old/already-resolved ones "
            "with no visible accept/decline affordance."
        )
