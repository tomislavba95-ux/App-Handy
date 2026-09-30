"""Schnittstelle zu eBay: Anmeldung (OAuth), Preissuche, Bilder-Upload und Angebote."""

import base64
import time
import urllib.parse
from typing import Any

import httpx

from .config import Config

USER_SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account",
]
APP_SCOPE = "https://api.ebay.com/oauth/api_scope"

# Zustand ungradeter Karten -> eBay-Zustandsbeschreibung "Card Condition" (40001).
# Sammelkartenspiele (Pokémon, Yu-Gi-Oh!) und Sportkarten nutzen verschiedene Werte.
CARD_CONDITION_IDS_TCG = {
    "NM": "400010",  # Near Mint or Better
    "EX": "400015",  # Lightly Played (Excellent)
    "VG": "400016",  # Moderately Played (Very Good)
    "POOR": "400017",  # Heavily Played (Poor)
}
CARD_CONDITION_IDS_SPORTS = {
    "NM": "400010",  # Near Mint or Better
    "EX": "400011",  # Excellent
    "VG": "400012",  # Very Good
    "POOR": "400013",  # Poor
}


class EbayError(Exception):
    offer_id: str | None = None


def _error_text(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}: {resp.text[:300]}"
    errors = data.get("errors") or []
    if errors:
        return "; ".join(e.get("longMessage") or e.get("message") or str(e) for e in errors)
    return f"HTTP {resp.status_code}: {data}"


class EbayClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        sandbox = cfg.is_sandbox
        self.api = "https://api.sandbox.ebay.com" if sandbox else "https://api.ebay.com"
        self.apim = "https://apim.sandbox.ebay.com" if sandbox else "https://apim.ebay.com"
        self.auth = "https://auth.sandbox.ebay.com" if sandbox else "https://auth.ebay.com"
        self.item_url = "https://www.sandbox.ebay.com/itm/" if sandbox else "https://www.ebay.de/itm/"
        self.http = httpx.AsyncClient(timeout=60)
        self._tokens: dict[str, tuple[str, float]] = {}
        self._aspect_cache: dict[str, list[dict]] = {}
        self._policies: dict[str, str] | None = None

    # ---------- Anmeldung ----------

    def _basic_auth(self) -> str:
        raw = f"{self.cfg.ebay_client_id}:{self.cfg.ebay_client_secret}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    async def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        resp = await self.http.post(
            f"{self.api}/identity/v1/oauth2/token",
            data=data,
            headers={
                "Authorization": self._basic_auth(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        if resp.status_code != 200:
            raise EbayError(f"eBay-Anmeldung fehlgeschlagen: {resp.text[:300]}")
        return resp.json()

    async def _token(self, kind: str) -> str:
        cached = self._tokens.get(kind)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        if kind == "app":
            data = await self._token_request({"grant_type": "client_credentials", "scope": APP_SCOPE})
        else:
            if not self.cfg.ebay_refresh_token:
                raise EbayError("EBAY_REFRESH_TOKEN fehlt. Bitte zuerst `python ebay_login.py` ausführen.")
            data = await self._token_request(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": self.cfg.ebay_refresh_token,
                    "scope": " ".join(USER_SCOPES),
                }
            )
        self._tokens[kind] = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
        return data["access_token"]

    def consent_url(self) -> str:
        query = urllib.parse.urlencode(
            {
                "client_id": self.cfg.ebay_client_id,
                "redirect_uri": self.cfg.ebay_ru_name,
                "response_type": "code",
                "scope": " ".join(USER_SCOPES),
            }
        )
        return f"{self.auth}/oauth2/authorize?{query}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.cfg.ebay_ru_name,
            }
        )

    async def _request(self, method: str, url: str, token_kind: str = "user", **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {await self._token(token_kind)}"
        headers.setdefault("X-EBAY-C-MARKETPLACE-ID", self.cfg.ebay_marketplace)
        resp = await self.http.request(method, url, headers=headers, **kwargs)
        if resp.status_code >= 400:
            raise EbayError(_error_text(resp))
        return resp

    # ---------- Kategorien & Merkmale ----------

    async def item_aspects(self, category_id: str) -> list[dict]:
        """Artikelmerkmale (z. B. Spiel, Set, Sprache), die eBay für die Kategorie erwartet."""
        if category_id in self._aspect_cache:
            return self._aspect_cache[category_id]
        resp = await self._request(
            "GET",
            f"{self.api}/commerce/taxonomy/v1/get_default_category_tree_id",
            token_kind="app",
            params={"marketplace_id": self.cfg.ebay_marketplace},
        )
        tree_id = resp.json()["categoryTreeId"]
        resp = await self._request(
            "GET",
            f"{self.api}/commerce/taxonomy/v1/category_tree/{tree_id}/get_item_aspects_for_category",
            token_kind="app",
            params={"category_id": category_id},
        )
        aspects = []
        for a in resp.json().get("aspects", []):
            c = a.get("aspectConstraint", {})
            required = c.get("aspectRequired", False)
            if not required and c.get("aspectUsage") != "RECOMMENDED":
                continue
            values = [v["localizedValue"] for v in a.get("aspectValues", [])]
            aspects.append(
                {
                    "name": a["localizedAspectName"],
                    "required": required,
                    "selection_only": c.get("aspectMode") == "SELECTION_ONLY",
                    "values": values[:40],
                }
            )
        self._aspect_cache[category_id] = aspects
        return aspects

    # ---------- Preise ----------

    async def search_prices(self, query: str, category_id: str) -> list[dict]:
        """Aktuelle Sofort-Kaufen-Angebote für die Suche (Preis + Titel)."""
        resp = await self._request(
            "GET",
            f"{self.api}/buy/browse/v1/item_summary/search",
            token_kind="app",
            params={
                "q": query,
                "category_ids": category_id,
                "filter": "buyingOptions:{FIXED_PRICE}",
                "limit": "50",
            },
        )
        items = []
        for it in resp.json().get("itemSummaries", []):
            price = it.get("price", {})
            if price.get("currency") != "EUR":
                continue
            items.append({"title": it.get("title", ""), "price": float(price["value"])})
        return items

    # ---------- Verkaufen ----------

    async def policies(self) -> dict[str, str]:
        """Versand-, Zahlungs- und Rücknahme-Richtlinien (aus .env oder die erste im Konto)."""
        if self._policies:
            return self._policies
        result = {
            "fulfillmentPolicyId": self.cfg.ebay_fulfillment_policy_id,
            "paymentPolicyId": self.cfg.ebay_payment_policy_id,
            "returnPolicyId": self.cfg.ebay_return_policy_id,
        }
        lookups = {
            "fulfillmentPolicyId": ("fulfillment_policy", "fulfillmentPolicies"),
            "paymentPolicyId": ("payment_policy", "paymentPolicies"),
            "returnPolicyId": ("return_policy", "returnPolicies"),
        }
        for key, (path, list_key) in lookups.items():
            if result[key]:
                continue
            resp = await self._request(
                "GET",
                f"{self.api}/sell/account/v1/{path}",
                params={"marketplace_id": self.cfg.ebay_marketplace},
            )
            found = resp.json().get(list_key) or []
            if not found:
                raise EbayError(
                    f"Keine {path} in deinem eBay-Konto gefunden. Bitte in eBay unter "
                    "Konto > Geschäftsrichtlinien anlegen (siehe README)."
                )
            result[key] = found[0][key]
        self._policies = result
        return result

    async def upload_image(self, data: bytes, filename: str, content_type: str) -> str:
        resp = await self._request(
            "POST",
            f"{self.apim}/commerce/media/v1_beta/image/create_image_from_file",
            files={"image": (filename, data, content_type)},
        )
        try:
            url = resp.json().get("imageUrl")
        except ValueError:
            url = None
        if not url and resp.headers.get("Location"):
            url = (await self._request("GET", resp.headers["Location"])).json().get("imageUrl")
        if not url:
            raise EbayError("Bild-Upload zu eBay lieferte keine Bild-URL.")
        return url

    async def create_listing(
        self,
        sku: str,
        title: str,
        description_html: str,
        aspects: dict[str, list[str]],
        image_urls: list[str],
        condition: str,
        is_sports: bool,
        category_id: str,
        price: float,
        offer_id: str | None = None,
    ) -> tuple[str, str]:
        """Legt Artikel + Angebot an und veröffentlicht es. Gibt (offer_id, listing_id) zurück."""
        lang = {"Content-Language": "de-DE"}
        condition_ids = CARD_CONDITION_IDS_SPORTS if is_sports else CARD_CONDITION_IDS_TCG
        await self._request(
            "PUT",
            f"{self.api}/sell/inventory/v1/inventory_item/{sku}",
            headers=dict(lang),
            json={
                "availability": {"shipToLocationAvailability": {"quantity": 1}},
                "condition": "USED_VERY_GOOD",  # = 4000 "Ungraded" bei Sammelkarten
                "conditionDescriptors": [
                    {"name": "40001", "values": [condition_ids.get(condition, "400010")]}
                ],
                "product": {
                    "title": title,
                    "description": description_html,
                    "aspects": aspects,
                    "imageUrls": image_urls,
                },
            },
        )
        offer = {
            "sku": sku,
            "marketplaceId": self.cfg.ebay_marketplace,
            "format": "FIXED_PRICE",
            "availableQuantity": 1,
            "categoryId": category_id,
            "listingDescription": description_html,
            "listingPolicies": await self.policies(),
            "pricingSummary": {"price": {"value": f"{price:.2f}", "currency": "EUR"}},
            "merchantLocationKey": self.cfg.ebay_location_key,
        }
        if offer_id:
            await self._request(
                "PUT", f"{self.api}/sell/inventory/v1/offer/{offer_id}", headers=dict(lang), json=offer
            )
        else:
            resp = await self._request(
                "POST", f"{self.api}/sell/inventory/v1/offer", headers=dict(lang), json=offer
            )
            offer_id = resp.json()["offerId"]
        try:
            resp = await self._request("POST", f"{self.api}/sell/inventory/v1/offer/{offer_id}/publish")
        except EbayError as e:
            # offer_id merken, damit ein erneuter Versuch das Angebot aktualisiert statt neu anlegt
            e.offer_id = offer_id
            raise
        return offer_id, resp.json()["listingId"]

    # ---------- Einrichtung ----------

    async def ensure_location(self, postal_code: str, city: str, country: str = "DE") -> None:
        key = self.cfg.ebay_location_key
        try:
            await self._request("GET", f"{self.api}/sell/inventory/v1/location/{key}")
            return
        except EbayError:
            pass
        await self._request(
            "POST",
            f"{self.api}/sell/inventory/v1/location/{key}",
            json={
                "location": {"address": {"postalCode": postal_code, "city": city, "country": country}},
                "locationTypes": ["WAREHOUSE"],
                "name": "Versandort",
                "merchantLocationStatus": "ENABLED",
            },
        )

    async def opt_in_business_policies(self) -> None:
        try:
            await self._request(
                "POST",
                f"{self.api}/sell/account/v1/program/opt_in",
                json={"programType": "SELLING_POLICY_MANAGEMENT"},
            )
        except EbayError:
            pass  # bereits angemeldet

    async def close(self) -> None:
        await self.http.aclose()
