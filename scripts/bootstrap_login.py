"""Run this ONCE on your own computer (not on the VPS) to log into Vinted.

This opens a real, visible browser window. You log in by hand - including
any 2FA/captcha - exactly like you always do. Nothing here automates the
login itself; it only saves the resulting session afterwards.

The output file (vinted_session.json) contains your login cookies. Treat it
like a password:
- Never commit it to git (it's already in .gitignore).
- Copy it to the VPS over scp/ssh, not anywhere public.
- If you ever think it leaked, log out of Vinted everywhere (invalidates it)
  and run this script again.

Usage:
    pip install playwright
    playwright install chromium
    python scripts/bootstrap_login.py
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "vinted_session.json"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="de-DE")
        page = context.new_page()
        page.goto("https://www.vinted.de/")

        print("\nEin Browserfenster hat sich geöffnet.")
        print("Logg dich dort ganz normal bei Vinted ein (inkl. evtl. 2FA/Captcha).")
        input("Wenn du eingeloggt bist und deinen Feed siehst, drück hier Enter... ")

        context.storage_state(path=str(OUTPUT_PATH))
        browser.close()

    print(f"\nSession gespeichert: {OUTPUT_PATH}")
    print("Kopier diese Datei jetzt auf deinen VPS, z.B.:")
    print(f"  scp {OUTPUT_PATH} user@dein-server:/opt/vintedautomate/vinted_session.json")


if __name__ == "__main__":
    sys.exit(main())
