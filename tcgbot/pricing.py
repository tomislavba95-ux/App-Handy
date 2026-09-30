"""Preisvorschlag aus aktuellen eBay-Angeboten und Cardmarket-Preisen."""

import logging
import math
import re
import statistics

import httpx

from .config import Config
from .ebay import EbayClient, EbayError

log = logging.getLogger(__name__)

# Angebote mit diesen Wörtern im Titel sind keine vergleichbare Einzelkarte
EXCLUDE_WORDS = [
    "psa", "bgs", "cgc", "beckett", "sgc", "graded", "konvolut", "sammlung", "lot ", "bundle",
    "booster", "display", "proxy", "fake", "custom", "orica", "wählen", "auswahl", "choose",
]

# Cardmarket-Trendpreise gelten für Near Mint; schlechtere Zustände entsprechend günstiger
CONDITION_FACTOR = {"NM": 1.0, "EX": 0.8, "VG": 0.6, "POOR": 0.35}


def _percentile(values: list[float], p: float) -> float:
    values = sorted(values)
    k = (len(values) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def _remove_outliers(values: list[float]) -> list[float]:
    if len(values) < 4:
        return values
    q1, q3 = _percentile(values, 0.25), _percentile(values, 0.75)
    iqr = q3 - q1
    return [v for v in values if q1 - 1.5 * iqr <= v <= q3 + 1.5 * iqr]


def round_price(value: float, minimum: float) -> float:
    """Auf typische Verkaufspreise runden: x,49 / x,99 unter 20 €, sonst ganze Euro minus 1 Cent."""
    if value < 20:
        price = math.floor(value * 2) / 2 - 0.01
        if price < value - 0.5:
            price += 0.5
    else:
        price = round(value) - 0.01
    return round(max(price, minimum), 2)


def _number_core(number: str) -> str:
    """'025/198' -> '25', 'LOB-DE001' -> 'LOB-DE001'."""
    part = number.split("/")[0].strip()
    return part.lstrip("0") or part if part.isdigit() else part


class PriceFinder:
    def __init__(self, cfg: Config, ebay: EbayClient | None):
        self.cfg = cfg
        self.ebay = ebay
        self.http = httpx.AsyncClient(timeout=30)

    async def ebay_reference(self, card: dict, category_id: str) -> dict | None:
        if not self.ebay or not card.get("search_query"):
            return None
        try:
            items = await self.ebay.search_prices(card["search_query"], category_id)
        except EbayError as e:
            log.warning("eBay-Preissuche fehlgeschlagen: %s", e)
            return None
        number = _number_core(card.get("card_number", "")).lower()
        prices = []
        for it in items:
            title = it["title"].lower() + " "
            if any(w in title for w in EXCLUDE_WORDS):
                continue
            if number and len(number) >= 2 and number not in title:
                continue
            prices.append(it["price"])
        prices = _remove_outliers(prices)
        if len(prices) < 3:
            return None
        return {
            "source": "eBay (aktuelle Angebote)",
            "count": len(prices),
            "min": min(prices),
            "median": statistics.median(prices),
            # Angebote liegen meist über dem echten Verkaufspreis -> unteres Drittel als Referenz
            "value": _percentile(prices, 0.35),
        }

    async def pokemon_reference(self, card: dict) -> dict | None:
        name = card.get("card_name_en") or card.get("card_name")
        number = _number_core(card.get("card_number", ""))
        if not name:
            return None
        query = f'name:"{name}"' + (f" number:{number}" if number and number.isalnum() else "")
        headers = {"X-Api-Key": self.cfg.pokemontcg_api_key} if self.cfg.pokemontcg_api_key else {}
        try:
            resp = await self.http.get(
                "https://api.pokemontcg.io/v2/cards", params={"q": query, "pageSize": 20}, headers=headers
            )
            resp.raise_for_status()
            cards = resp.json().get("data", [])
        except (httpx.HTTPError, ValueError) as e:
            log.warning("pokemontcg.io fehlgeschlagen: %s", e)
            return None

        set_code = card.get("set_code", "").lower()
        set_name = card.get("set_name", "").lower()
        if len(cards) > 1 and (set_code or set_name):
            narrowed = [
                c for c in cards
                if set_code and set_code in (c["set"].get("ptcgoCode", "").lower(), c["set"]["id"].lower())
                or set_name and set_name in c["set"]["name"].lower()
            ]
            cards = narrowed or cards

        reverse = "reverse" in card.get("variant", "").lower()
        values = []
        for c in cards:
            prices = (c.get("cardmarket") or {}).get("prices") or {}
            v = prices.get("reverseHoloTrend") if reverse else None
            v = v or prices.get("trendPrice") or prices.get("averageSellPrice")
            if v:
                values.append(float(v))
        if not values:
            return None
        factor = CONDITION_FACTOR.get(card.get("condition", "NM"), 1.0)
        note = "" if len(values) == 1 else f" ({len(values)} mögliche Drucke)"
        return {
            "source": f"Cardmarket-Trend{note}",
            "count": len(values),
            "value": statistics.median(values) * factor,
            "raw": statistics.median(values),
        }

    async def yugioh_reference(self, card: dict) -> dict | None:
        name = card.get("card_name_en")
        if not name:
            return None
        try:
            resp = await self.http.get("https://db.ygoprodeck.com/api/v7/cardinfo.php", params={"name": name})
            if resp.status_code != 200:
                return None
            data = resp.json().get("data", [])
        except (httpx.HTTPError, ValueError) as e:
            log.warning("ygoprodeck fehlgeschlagen: %s", e)
            return None
        if not data:
            return None
        price = float((data[0].get("card_prices") or [{}])[0].get("cardmarket_price") or 0)
        if not price:
            return None
        factor = CONDITION_FACTOR.get(card.get("condition", "NM"), 1.0)
        return {"source": "Cardmarket (günstigster Druck)", "count": 1, "value": price * factor, "raw": price}

    async def suggest(self, card: dict, category_id: str) -> dict:
        refs = []
        ebay_ref = await self.ebay_reference(card, category_id)
        if ebay_ref:
            refs.append(ebay_ref)
        game = card.get("game")
        if game == "pokemon":
            ref = await self.pokemon_reference(card)
        elif game == "yugioh":
            ref = await self.yugioh_reference(card)
        else:
            ref = None
        if ref:
            refs.append(ref)

        if not refs:
            return {"price": None, "refs": []}
        value = statistics.mean(r["value"] for r in refs)
        return {"price": round_price(value, self.cfg.min_price), "refs": refs}

    async def close(self) -> None:
        await self.http.aclose()


def parse_price(text: str) -> float | None:
    """'12,50', '12.5 €', '12' -> 12.5"""
    m = re.search(r"\d+(?:[.,]\d{1,2})?", text.replace(" ", ""))
    if not m:
        return None
    return float(m.group(0).replace(",", "."))
