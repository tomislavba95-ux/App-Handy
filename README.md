# App-Handy – Sammelkarten per Telegram auf eBay verkaufen

Du schickst einem Telegram-Bot Fotos deiner Karten. Der Bot erkennt die Karte,
schlägt einen Preis vor und stellt sie **erst nach deiner Bestätigung** als
Sofort-Kaufen-Angebot auf eBay.de ein.

Unterstützt: **Pokémon, Yu-Gi-Oh!, Fußball- und Basketball-Karten** (ungegradet, Einzelkarten).

## So läuft es ab

1. Du schickst Vorder- und Rückseite **zusammen** (beide Fotos auswählen, gemeinsam senden).
2. Die KI (Claude) liest Name, Set, Nummer, Sprache und Seltenheit ab und schätzt den Zustand.
3. Der Bot sucht Vergleichspreise:
   - aktuelle eBay-Angebote derselben Karte (gegradete Karten, Lots und Ausreißer werden aussortiert)
   - bei Pokémon und Yu-Gi-Oh! zusätzlich der Cardmarket-Preis
4. Du bekommst eine Vorschau mit Knöpfen:
   **✅ Auf eBay einstellen · 💶 Preis ändern · 📝 Titel ändern · 📦 Zustand ändern · 🗑 Verwerfen**
5. Nach ✅ lädt der Bot die Fotos zu eBay hoch und stellt die Karte ein. Du bekommst den Link.

Befehle im Chat: `/offen` (wartet auf Bestätigung), `/online` (schon auf eBay), `/ebay` (eBay verbinden), `/hilfe`.

## Einrichtung nur mit dem Handy

👉 **[ANLEITUNG_HANDY.md](ANLEITUNG_HANDY.md)**: Schritt für Schritt, ohne PC.
Der Bot läuft dabei auf einem Online-Server (Railway), und eBay verbindest du im Chat mit `/ebay`.

## Einrichtung am PC (einmalig, ca. 30–45 Minuten)

Du brauchst einen Computer mit **Python 3.10 oder neuer**. Später kann der Bot auch auf
einem kleinen Server laufen, dann muss dein PC nicht an sein (siehe unten).

### Schritt 1: Programm installieren

```bash
git clone https://github.com/tomislavba95-ux/App-Handy.git
cd App-Handy
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

Alle Schlüssel kommen in die Datei `.env`. **Gib diese Datei niemals weiter.**

### Schritt 2: Telegram-Bot und Claude-Schlüssel

1. In Telegram den Kontakt **@BotFather** öffnen, `/newbot` senden und einen Namen wählen.
   Den Token, den du bekommst, in `.env` bei `TELEGRAM_BOT_TOKEN=` eintragen.
2. Auf [console.anthropic.com](https://console.anthropic.com) ein Konto anlegen, Guthaben aufladen
   (10 € reichen für etwa 150 Karten) und einen API-Schlüssel erstellen.
   In `.env` bei `ANTHROPIC_API_KEY=` eintragen.
3. Bot starten: `python run_bot.py`. Schreib deinem Bot in Telegram `/start`.
   Er antwortet mit deiner Telegram-ID. Die bei `ALLOWED_TELEGRAM_USER_IDS=` eintragen
   und den Bot neu starten (Strg+C, dann wieder `python run_bot.py`).
   So kann **nur du** den Bot benutzen.

Ab jetzt erkennt der Bot schon Karten und schätzt Preise. Zum Einstellen fehlt noch eBay.

### Schritt 3: eBay verbinden

1. Auf [developer.ebay.com](https://developer.ebay.com) mit deinem eBay-Konto ein
   Entwicklerkonto anlegen (kostenlos). Die Freischaltung kann 1–2 Tage dauern.
2. Unter **Application Keys** ein Schlüsselpaar erstellen, zuerst für **Sandbox** (Testumgebung).
   `App ID (Client ID)` → `EBAY_CLIENT_ID`, `Cert ID (Client Secret)` → `EBAY_CLIENT_SECRET`.
3. Unter **User Tokens → Get a Token from eBay via Your Application** eine
   Weiterleitungs-Adresse anlegen. Den Namen, der wie `Dein_Name-DeinName-App-abcde` aussieht
   (der **RuName**), bei `EBAY_RU_NAME=` eintragen.
4. Im **eBay-Konto** (Mein eBay → Konto → Geschäftsrichtlinien) je eine Richtlinie anlegen für
   - **Versand** (z. B. „Brief mit Sendungsverfolgung“ oder „Warensendung“, Kosten eintragen)
   - **Zahlung** (eBay-Zahlungsabwicklung)
   - **Rücknahme** (z. B. 30 Tage)
5. `python ebay_login.py` ausführen und den Anweisungen folgen: Link öffnen, bei eBay
   anmelden, zustimmen, die Adresse aus dem Browser zurückkopieren, Postleitzahl und Ort
   eingeben. Das Skript speichert alles in `.env`.
6. Bot neu starten und mit ein paar Karten testen. In der Sandbox sind die Angebote nicht echt.

**Wenn alles klappt:** Schritt 3.2, 3.3 und 3.5 mit den **Production**-Schlüsseln
wiederholen und `EBAY_ENV=production` setzen. Ab dann sind die Angebote echt auf eBay.de.

## Kosten

| Posten | Kosten |
|---|---|
| Telegram, eBay-Entwicklerkonto, pokemontcg.io, ygoprodeck | kostenlos |
| Kartenerkennung (Claude) | ca. 3–8 Cent pro Karte (100 Karten ≈ 5 €) |
| eBay-Verkaufsgebühren | wie bei normalem Verkauf (für Privatverkäufer in DE derzeit meist 0 €, Stand prüfen) |
| Server (optional) | ab ca. 4 €/Monat |

## Wichtige Hinweise

- **Prüf jede Vorschau.** Die KI kann Karten verwechseln (z. B. Reprints, andere Sprache)
  oder den Zustand falsch einschätzen. Deshalb gibt es die Bestätigung.
- **Preisvorschlag:** Aktuelle eBay-Angebote liegen meist über dem, was wirklich bezahlt wird.
  Der Bot nimmt deshalb das untere Drittel der Angebote, zusammen mit dem Cardmarket-Preis.
  Für Fußball und Basketball gibt es nur eBay als Quelle. Bei seltenen Karten findet er
  eventuell keinen Preis, dann gibst du ihn selbst ein.
- **Karten unter ca. 2 €** lohnen sich als Einzelangebot wegen Versand kaum.
- **Gegradete Karten** (PSA, BGS, CGC …) stellt der Bot noch nicht ein.
- **Steuer:** Ab 30 Verkäufen oder 2.000 € im Jahr meldet eBay deine Verkäufe ans Finanzamt (DAC7).
  Wer regelmäßig mit Gewinnabsicht verkauft, kann als gewerblich gelten. Im Zweifel beraten lassen.
- Fotos und Entwürfe liegen lokal im Ordner `data/`.

## Rund um die Uhr laufen lassen

Der Bot funktioniert nur, solange `python run_bot.py` läuft. Damit du jederzeit Fotos
schicken kannst, kann er auf einem kleinen Linux-Server laufen (z. B. Hetzner, ab ca. 4 €/Monat)
oder auf einem Raspberry Pi zu Hause. Dafür die Schritte 1–3 dort wiederholen
(oder die `.env` kopieren) und den Bot als Dienst starten.

## Für Entwickler

```
tcgbot/
  bot.py        Telegram-Ablauf (Fotos, Knöpfe, Einstellen)
  recognize.py  Kartenerkennung mit Claude (strukturierte JSON-Antwort)
  pricing.py    Preisvorschlag (eBay Browse API, pokemontcg.io, ygoprodeck)
  ebay.py       eBay OAuth, Taxonomy, Media, Inventory und Account API
  storage.py    SQLite-Speicher für Entwürfe
run_bot.py      Startet den Bot
ebay_login.py   Einmalige eBay-Anmeldung und Einrichtung
tests/          python -m pytest
```
