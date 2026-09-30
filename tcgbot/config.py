"""Einstellungen aus der Datei .env bzw. aus Umgebungsvariablen."""

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimaler .env-Leser (KEY=VALUE pro Zeile), ohne Zusatzpaket."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_dotenv(BASE_DIR / ".env")

# Speicherort für Fotos und Entwürfe (auf einem Server auf ein dauerhaftes Volume zeigen lassen)
DATA_DIR = Path(os.environ.get("DATA_DIR") or BASE_DIR / "data")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Config:
    telegram_token: str = field(default_factory=lambda: _get("TELEGRAM_BOT_TOKEN"))
    allowed_user_ids: set[int] = field(
        default_factory=lambda: {
            int(x) for x in _get("ALLOWED_TELEGRAM_USER_IDS").replace(" ", "").split(",") if x
        }
    )

    anthropic_model: str = field(default_factory=lambda: _get("ANTHROPIC_MODEL", "claude-opus-5-5"))

    ebay_env: str = field(default_factory=lambda: _get("EBAY_ENV", "sandbox").lower())
    ebay_client_id: str = field(default_factory=lambda: _get("EBAY_CLIENT_ID"))
    ebay_client_secret: str = field(default_factory=lambda: _get("EBAY_CLIENT_SECRET"))
    ebay_ru_name: str = field(default_factory=lambda: _get("EBAY_RU_NAME"))
    ebay_refresh_token: str = field(default_factory=lambda: _get("EBAY_REFRESH_TOKEN"))
    ebay_marketplace: str = field(default_factory=lambda: _get("EBAY_MARKETPLACE", "EBAY_DE"))
    ebay_location_key: str = field(default_factory=lambda: _get("EBAY_LOCATION_KEY", "zuhause"))
    ebay_fulfillment_policy_id: str = field(default_factory=lambda: _get("EBAY_FULFILLMENT_POLICY_ID"))
    ebay_payment_policy_id: str = field(default_factory=lambda: _get("EBAY_PAYMENT_POLICY_ID"))
    ebay_return_policy_id: str = field(default_factory=lambda: _get("EBAY_RETURN_POLICY_ID"))

    # eBay-Kategorien (auf eBay.de):
    # 183454 = Einzelne Trading Card Game Karten (Pokémon, Yu-Gi-Oh!, ...)
    # 261328 = Einzelne Sport-Sammelkarten (Fußball, Basketball, ...)
    category_tcg: str = field(default_factory=lambda: _get("EBAY_CATEGORY_TCG", "183454"))
    category_sports: str = field(default_factory=lambda: _get("EBAY_CATEGORY_SPORTS", "261328"))

    min_price: float = field(default_factory=lambda: float(_get("MIN_PRICE", "0.99")))
    pokemontcg_api_key: str = field(default_factory=lambda: _get("POKEMONTCG_API_KEY"))
    shipping_note: str = field(
        default_factory=lambda: _get(
            "SHIPPING_NOTE",
            "Die Karte wird sicher in Kartenhülle und Toploader verschickt.",
        )
    )

    @property
    def ebay_configured(self) -> bool:
        return bool(self.ebay_client_id and self.ebay_client_secret)

    @property
    def ebay_can_sell(self) -> bool:
        return self.ebay_configured and bool(self.ebay_refresh_token)

    @property
    def is_sandbox(self) -> bool:
        return self.ebay_env != "production"


config = Config()
