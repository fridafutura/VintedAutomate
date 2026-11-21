# VintedAutomate

Entscheidungslogik für halbautomatisiertes Verkaufen auf Vinted: Angebote aus
Fotos + Notizen erstellen, Preise aus Vergleichsangeboten ableiten, und auf
Likes/Nachrichten mit klaren Rabattregeln reagieren.

## Wichtig: Architektur-Entscheidung

Dieses Paket enthält **bewusst keinen Vinted-Zugriff**. Vinted hat keine
offizielle Verkäufer-API; jede Automatisierung (Browser-Steuerung oder
interne API-Calls) verstößt wahrscheinlich gegen die Nutzungsbedingungen und
riskiert eine Account-Sperre. Deshalb ist die gesamte Geschäftslogik hier
hinter dem Interface `vinted_client.VintedClient` gekapselt - getestet gegen
`InMemoryMockVintedClient`, der nie das Netzwerk anfasst.

Offene Entscheidungen, die noch zu treffen sind, bevor es an echten
Vinted-Zugriff geht:

1. **Wo läuft es dauerhaft?** Eigener Rechner (Cronjob) vs. kleiner Server/VPS.
2. **Wie kommen Vergleichspreise rein?** Aktuell manuell (`PriceComp`-Liste);
   automatisiertes Scraping wäre ein eigener Risikoblock.
3. **Wie wird tatsächlich gepostet/geantwortet?** Browser-Automatisierung
   (z.B. Playwright) mit menschenähnlichem Timing, um das Sperrrisiko klein
   zu halten - aber nie auf null zu bringen.

Prüf außerdem, ob Vinted inzwischen eine eigene "Rabatt für Leute, die
gefallen hat"-Funktion anbietet - falls ja, wäre das risikofreier als ein
Nachbau.

### Bestätigt aus echten Vinted-Screenshots

- Das "Artikel verkaufen"-Formular ist: Fotos → Titel → Beschreibung →
  Kategorie → Preis. Felder wie Marke/Größe/Farbe/Zustand/Material tauchen
  erst nach der Kategoriewahl auf und unterscheiden sich je nach Kategorie -
  deshalb sind sie in `ListingFields` optional.
- Die Kategorie-Baumstruktur unterhalb der 7 Top-Level-Kategorien ist zu groß
  und veränderlich, um sie zu pflegen. Deshalb generiert `listing_generator.py`
  nur `category_top_level` (einer der 7 bekannten) plus `category_search_term`
  (z.B. "Pullover") - diesen Begriff würde die spätere Automatisierung in
  Vinteds eigenes Kategorie-Suchfeld eintippen und den besten Live-Treffer
  übernehmen, statt sich auf eine veraltete lokale Kategorie-Liste zu verlassen.
- Vinted hat ein **eingebautes strukturiertes Preisangebot** ("Verhandeln"-
  Button auf der Artikelseite): Käufer geben eine konkrete Zahl ein, kein
  Freitext. Das ist ein eigener Kanal neben dem normalen Chat und wird in
  `message_handler.handle_incoming_offer()` behandelt - mit derselben
  Rabatt-Engine wie Chat-Rabattwünsche, nur ohne Intent-Klassifizierung
  (die Zahl ist ja schon da).

## Geschäftsregeln (`config.py`)

| Regel | Wert | Wo |
|---|---|---|
| Preisuntergrenze | 8,00 € | immer, egal welcher Rabatt |
| Automatischer Like-Rabatt | 10% | `likes.py` |
| Standard-Rabattspanne pro Artikel | bis 15% | `config.py` (Richtwert) |
| Max. Rabatt ohne Rückfrage bei Käufer-Nachricht | 20% | `discounts.py` |

Diese Zahlen sind als Code-Konstanten hinterlegt, nicht nur als Prompt-Text -
die Preisuntergrenze und die Rabattgrenzen werden in `discounts.py` hart
durchgesetzt, unabhängig davon, was das LLM vorschlägt.

## Module

- `config.py` - Geschäftsregeln (Preisuntergrenze, Rabattsätze)
- `models.py` - Datentypen (Item, Listing, Nachrichten, Entscheidungen)
- `pricing.py` - Preisvorschlag aus Vergleichsangeboten (zustandsbereinigt)
- `discounts.py` - Rabatt-Entscheidungslogik, inkl. Preisuntergrenzen-Clamping
- `claude_client.py` - dünner Wrapper um die Anthropic-API (Vision + Text)
- `listing_generator.py` - Fotos + Notizen → vollständige Angebotsfelder
- `message_handler.py` - Käufer-Nachricht/Angebot → Auto-Antwort, Rabatt, oder Eskalation an dich
- `likes.py` - Like-Event → automatische Rabatt-Nachricht
- `vinted_client.py` - Interface + In-Memory-Mock (kein echter Vinted-Zugriff)

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python -m pytest tests/ -v
```

## Demos (gegen den Mock-Client, kein echter Vinted-Zugriff)

```bash
python scripts/create_listing_demo.py foto1.jpg foto2.jpg \
    --notes "Nike Hoodie, Größe M, kaum getragen" \
    --comp 15.0 --comp 18.0

python scripts/simulate_like_and_message_demo.py
```

## Deployment auf einem VPS (Hetzner)

Entscheidung: dauerhaft laufender Teil auf einem kleinen gemieteten Server,
da der heimische Laptop nicht durchgehend läuft (Details siehe Architektur-
Diskussion). Empfehlung: **Hetzner Cloud**, Typ CX22 (2 vCPU, 4GB RAM - reicht
für einen headless Chromium), Standort Nürnberg oder Falkenstein, ~4-5€/Monat.

### 1. Login lokal vorbereiten (auf deinem eigenen Rechner, NICHT auf dem VPS)

```bash
pip install playwright
playwright install chromium
python scripts/bootstrap_login.py
```

Ein Browserfenster öffnet sich, du loggst dich normal bei Vinted ein (inkl.
2FA/Captcha falls nötig), drückst dann Enter im Terminal. Das erzeugt
`vinted_session.json` - das ist deine Login-Session, wie ein Passwort zu
behandeln (landet nie in git, siehe `.gitignore`).

### 2. Server anlegen

1. Bei [hetzner.com/cloud](https://www.hetzner.com/cloud) Account anlegen.
2. Neuen Server: CX22, Ubuntu 24.04, Standort Nürnberg/Falkenstein.
3. SSH-Zugang einrichten (Hetzner führt dich durch SSH-Key-Upload).

### 3. Server einrichten

```bash
ssh root@<server-ip>
adduser --disabled-password --gecos "" vintedautomate
apt update && apt install -y python3-venv git

su - vintedautomate
git clone <dein-repo-url> /opt/vintedautomate   # oder per scp hochladen
cd /opt/vintedautomate
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install --with-deps chromium
```

### 4. Session + API-Key übertragen

Von deinem lokalen Rechner aus:

```bash
scp vinted_session.json root@<server-ip>:/opt/vintedautomate/vinted_session.json
```

Auf dem Server, `.env` anlegen (wird vom systemd-Service geladen):

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > /opt/vintedautomate/.env
chown vintedautomate:vintedautomate /opt/vintedautomate/.env /opt/vintedautomate/vinted_session.json
chmod 600 /opt/vintedautomate/.env /opt/vintedautomate/vinted_session.json
```

### 5. Als Dienst einrichten (läuft dauerhaft, startet nach Neustart automatisch)

```bash
cp /opt/vintedautomate/vintedautomate.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now vintedautomate
journalctl -u vintedautomate -f   # Logs live mitlesen
```

### Session erneuern

Vinted-Sessions laufen irgendwann ab. Der Agent erkennt das (`is_logged_in()`)
und loggt eine klare Fehlermeldung statt sich falsch zu verhalten. Dann einfach
Schritt 1+4 wiederholen.

## Nächster Schritt

`get_new_likes`, `get_new_messages`, `send_message` und `update_price` in
`vinted_playwright_client.py` sind noch `NotImplementedError`-Platzhalter -
die seitenseitige Posteingang/Benachrichtigungs-Oberfläche wurde noch nicht
gezeigt. Sobald Screenshots davon da sind (Posteingang-Liste, eine Konversation
mit einem eingegangenen Preisangebot, eine "jemand hat geliked"-Benachrichtigung
falls es sowas gibt), werden diese gegen die echten Selektoren implementiert.
