"""Einmalige Einrichtung: verbindet den Bot mit deinem eBay-Konto.

Aufruf: python ebay_login.py
"""

import asyncio
import urllib.parse

from tcgbot.config import BASE_DIR, config
from tcgbot.ebay import EbayClient, EbayError

ENV_FILE = BASE_DIR / ".env"


def save_env(key: str, value: str) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [line for line in lines if not line.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> None:
    if not (config.ebay_client_id and config.ebay_client_secret and config.ebay_ru_name):
        raise SystemExit("Bitte zuerst EBAY_CLIENT_ID, EBAY_CLIENT_SECRET und EBAY_RU_NAME in .env eintragen.")

    ebay = EbayClient(config)
    mode = "SANDBOX (Test)" if config.is_sandbox else "ECHT (eBay.de)"
    print(f"eBay-Modus: {mode}\n")
    print("1. Öffne diesen Link im Browser und melde dich bei eBay an:\n")
    print(ebay.consent_url())
    print("\n2. Nach dem Bestätigen landest du auf einer Seite. Kopiere die komplette Adresse")
    print("   aus der Adresszeile des Browsers und füge sie hier ein.\n")
    answer = input("Adresse: ").strip()
    code = urllib.parse.parse_qs(urllib.parse.urlparse(answer).query).get("code", [answer])[0]

    tokens = await ebay.exchange_code(code)
    config.ebay_refresh_token = tokens["refresh_token"]
    save_env("EBAY_REFRESH_TOKEN", tokens["refresh_token"])
    print("\n✅ Verbunden! Der Schlüssel wurde in .env gespeichert (gültig ca. 18 Monate).\n")

    await ebay.opt_in_business_policies()

    print("3. Von wo verschickst du die Karten?")
    postal_code = input("   Postleitzahl: ").strip()
    city = input("   Ort: ").strip()
    await ebay.ensure_location(postal_code, city)
    print(f"✅ Versandort gespeichert (Schlüssel: {config.ebay_location_key}).\n")

    try:
        policies = await ebay.policies()
        print("✅ Geschäftsrichtlinien gefunden:")
        for key, value in policies.items():
            print(f"   {key}: {value}")
    except EbayError as e:
        print(f"⚠️  {e}")
        print("   Lege in eBay je eine Richtlinie für Versand, Zahlung und Rücknahme an")
        print("   und starte dieses Skript danach erneut.")

    await ebay.close()
    print("\nFertig! Starte jetzt den Bot mit: python run_bot.py")


if __name__ == "__main__":
    asyncio.run(main())
