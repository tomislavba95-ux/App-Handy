"""Startet den Telegram-Bot. Aufruf: python run_bot.py"""

import logging

from tcgbot.bot import build_app

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

if __name__ == "__main__":
    print("Bot läuft. Beenden mit Strg+C.")
    build_app().run_polling()
