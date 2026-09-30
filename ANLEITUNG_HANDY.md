# Anleitung: Alles nur mit dem Handy einrichten

Du brauchst keinen PC. Der Bot läuft auf einem Online-Server (Railway),
du bedienst alles über Telegram und den Browser auf dem Handy.

**Dauer:** ca. 1 Stunde, plus 1–2 Tage Wartezeit auf die eBay-Freischaltung.
**Kosten:** Server ca. 5 $/Monat, KI-Erkennung ca. 5 € für 100 Karten.

> **Tipp zum Kopieren auf dem Handy**
> - Text lange gedrückt halten → „Kopieren“.
> - Adresse einer Webseite kopieren: oben in die Adresszeile tippen → „Alles auswählen“ → „Kopieren“.
> - Manche Seiten sind am Handy unübersichtlich. Dann im Browser-Menü (⋮ oder „Aa“)
>   **„Desktop-Website“** einschalten.

---

## Teil 1: Telegram-Bot anlegen (5 Minuten)

1. Telegram öffnen und oben nach **@BotFather** suchen (blauer Haken).
2. **Starten** tippen, dann `/newbot` schicken.
3. Einen Namen schicken, z. B. `Meine Karten`.
4. Einen Benutzernamen schicken, der auf `bot` endet, z. B. `tomis_karten_bot`.
5. BotFather schickt dir einen langen **Token** (sieht aus wie `123456789:ABCdef...`).
   Lange drücken → kopieren → in die Notizen-App einfügen.

## Teil 2: Schlüssel für die Kartenerkennung (5 Minuten)

1. Im Browser **console.anthropic.com** öffnen und ein Konto anlegen.
2. Unter **Billing** Guthaben aufladen (10 € reichen für etwa 150 Karten).
3. Unter **API Keys** → **Create Key** → Namen eingeben, z. B. `karten`.
4. Den Schlüssel (beginnt mit `sk-ant-`) kopieren und in die Notizen einfügen.
   **Er wird nur einmal angezeigt!**

## Teil 3: Den Bot online starten (10 Minuten)

1. Im Browser **railway.com** öffnen → **Login** → **Continue with GitHub**
   (mit deinem GitHub-Konto `tomislavba95-ux`).
2. **New Project** → **Deploy from GitHub repo** → **App-Handy** auswählen.
   Falls das Projekt nicht auftaucht: **Configure GitHub App** tippen und Railway den Zugriff
   auf App-Handy erlauben.
3. Auf das Kästchen **App-Handy** tippen → **Settings** → bei **Source / Branch** den Branch
   `ccr-ca1f0271-4gts8v` auswählen. Das ist nicht nötig, wenn der Code schon im
   Branch `main` liegt.
4. Tab **Variables** → **New Variable**. Diese drei eintragen:

   | Name | Wert |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | der Token aus Teil 1 |
   | `ANTHROPIC_API_KEY` | der Schlüssel aus Teil 2 |
   | `DATA_DIR` | `/data` |

5. Speicher anlegen, damit deine Karten bei einem Neustart nicht verloren gehen:
   im Projekt **+ Create** (oder **+ New**) → **Volume** → mit **App-Handy** verbinden,
   **Mount Path** = `/data`.
6. Oben **Deploy** tippen (falls es nicht von selbst startet). Nach 1–2 Minuten steht bei
   **Deployments** „Active“ bzw. „Success“. Unter **View Logs** steht dann `Bot läuft`.

Railway gibt dir am Anfang ein kleines Startguthaben. Danach braucht es den
**Hobby-Plan (5 $/Monat)**, sonst stoppt der Bot.

## Teil 4: Den Bot nur für dich freischalten (2 Minuten)

1. In Telegram deinen Bot suchen (den Benutzernamen aus Teil 1) → **Starten**.
2. Der Bot antwortet: **„Deine Telegram-ID ist 12345678.“** Die Zahl kopieren.
3. In Railway → **Variables** → neue Variable:
   `ALLOWED_TELEGRAM_USER_IDS` = deine Zahl.
4. Railway startet den Bot automatisch neu. Nach 1–2 Minuten nochmal `/start` schicken.
   Jetzt begrüßt er dich.

**Schon jetzt testen:** Schick ein Foto einer Karte. Der Bot erkennt sie und schätzt einen Preis.
Einstellen kann er noch nicht, dafür kommt jetzt eBay.

## Teil 5: eBay-Entwicklerkonto (15 Minuten + Wartezeit)

1. Im Browser **developer.ebay.com** → **Register** → mit deinem normalen eBay-Konto anmelden
   und das Formular ausfüllen. **Freischaltung dauert oft 1–2 Tage** (du bekommst eine E-Mail).
2. Nach der Freischaltung: oben **Hi [Name]** → **Application Keysets**.
   Einen Namen eingeben (z. B. `Karten`) und bei **Sandbox** auf **Create a keyset** tippen.
3. Du siehst drei Werte. Diese zwei brauchst du:
   - **App ID (Client ID)**
   - **Cert ID (Client Secret)**
4. Neben dem Sandbox-Keyset auf **User Tokens** tippen →
   **Get a Token from eBay via Your Application** → **Add eBay Redirect URL**.
   - **Display Title:** `Karten`
   - **Your privacy policy URL:** `https://github.com/tomislavba95-ux/App-Handy`
   - **Your auth accepted URL:** so lassen, wie es ist
   - **Save** tippen.
5. Jetzt steht dort ein **RuName**, ein Wert, der ungefähr so aussieht:
   `Tomislav_B-Tomislav-Karten-abcdefg`. Kopieren.
6. In Railway → **Variables** diese drei eintragen:

   | Name | Wert |
   |---|---|
   | `EBAY_CLIENT_ID` | App ID |
   | `EBAY_CLIENT_SECRET` | Cert ID |
   | `EBAY_RU_NAME` | RuName |

## Teil 6: eBay mit dem Bot verbinden (5 Minuten)

1. 1–2 Minuten warten, bis Railway neu gestartet hat. Dann dem Bot `/ebay` schicken.
2. Auf den Link tippen, mit deinem **Sandbox-Testkonto** anmelden (siehe Hinweis unten)
   und **Zustimmen** (Agree) tippen.
3. Du landest auf einer eBay-Seite. Die **ganze Adresse** aus der Adresszeile kopieren
   und dem Bot schicken.
4. Der Bot fragt nach deinem Versandort. Schick z. B. `10115 Berlin`.
5. Fehlen im eBay-Konto die Versand-, Zahlungs- oder Rücknahme-Regeln, sagt dir der Bot das.
   Dann weiter mit Teil 7.

> **Hinweis Sandbox:** Das ist eBays Testwelt. Dafür brauchst du ein eigenes Testkonto:
> developer.ebay.com → **Sandbox users** (bei den User Tokens) → **Create a new Sandbox user**.
> Mit diesem Konto meldest du dich in Schritt 2 an. In der Sandbox wird **nichts echt verkauft**.

## Teil 7: Versand-, Zahlungs- und Rücknahme-Regeln (10 Minuten)

eBay verlangt drei Regeln, die bei jedem Angebot verwendet werden.

1. Im Browser bei eBay anmelden (Sandbox: **sandbox.ebay.com**, später echt: **ebay.de**).
   **„Desktop-Website“** einschalten.
2. **Mein eBay** → **Konto** → **Geschäftsrichtlinien** (Business policies).
3. Drei Regeln anlegen:
   - **Versand:** z. B. „Deutsche Post Brief“ oder „Warensendung“ mit deinem Preis.
     Für wertvolle Karten besser mit Sendungsverfolgung.
   - **Zahlung:** Standard übernehmen.
   - **Rücknahme:** z. B. „Rücknahme innerhalb von 30 Tagen“ oder „keine Rücknahme“.
4. Fertig. Du musst `/ebay` nicht nochmal machen.

## Teil 8: Testen

1. Dem Bot die Vorder- und Rückseite einer Karte schicken, **beide Fotos auf einmal**
   (in der Galerie beide auswählen → senden).
2. Vorschau prüfen, eventuell Preis ändern → **✅ Auf eBay einstellen**.
3. Du bekommst einen Link zum (Test-)Angebot. Antippen und anschauen.

## Teil 9: Auf echt umstellen

Wenn in der Sandbox alles klappt:

1. developer.ebay.com → **Application Keysets** → bei **Production** ein Keyset anlegen.
   Eventuell will eBay vorher, dass du die Frage zu „Marketplace Account Deletion“ beantwortest.
   Wähle dort **„Opt out“** / „I do not persist eBay data“.
2. Wie in Teil 5 die **User Tokens** und den **RuName** für **Production** anlegen.
3. In Railway die drei `EBAY_...`-Werte durch die Production-Werte ersetzen und neu hinzufügen:
   `EBAY_ENV` = `production`.
4. Dem Bot `/ebay` schicken und diesmal mit deinem **echten eBay-Konto** anmelden.
5. Bei ebay.de die drei Regeln aus Teil 7 anlegen, falls noch nicht vorhanden.

Ab jetzt sind deine Angebote **echt auf eBay.de**. 🎉

---

## Wenn etwas nicht klappt

| Problem | Lösung |
|---|---|
| Bot antwortet gar nicht | Railway → **Deployments** → **View Logs** ansehen. Steht dort ein Fehler, schick mir einen Screenshot. |
| „Deine Telegram-ID ist …“ kommt immer wieder | `ALLOWED_TELEGRAM_USER_IDS` in Railway prüfen (nur die Zahl, keine Leerzeichen). |
| „Erkennung fehlgeschlagen“ | Guthaben bei console.anthropic.com prüfen, `ANTHROPIC_API_KEY` richtig kopiert? |
| „Keine fulfillment_policy gefunden“ | Teil 7 machen. |
| Fehler beim Einstellen | Die Meldung steht unter der Karte. Oft fehlt ein Merkmal. Screenshot an mich. |
| eBay-Verbindung abgelaufen (nach ca. 18 Monaten) | Einfach nochmal `/ebay`. |
