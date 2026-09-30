"""Tests ohne echte Netzwerkzugriffe: python -m pytest"""

import asyncio
import json
from types import SimpleNamespace

import httpx

from tcgbot import bot
from tcgbot.config import Config
from tcgbot.ebay import EbayClient
from tcgbot.pricing import PriceFinder, parse_price, round_price
from tcgbot.recognize import CARD_SCHEMA, CardRecognizer
from tcgbot.storage import Storage

CARD = {
    "is_card": True,
    "game": "pokemon",
    "card_name": "Glurak ex",
    "card_name_en": "Charizard ex",
    "set_name": "151",
    "set_code": "MEW",
    "card_number": "199/165",
    "language": "Deutsch",
    "rarity": "Special Illustration Rare",
    "variant": "",
    "year": "2023",
    "player_or_character": "Glurak",
    "team": "",
    "manufacturer": "The Pokémon Company",
    "is_graded": False,
    "condition": "NM",
    "condition_notes": "",
    "confidence": "hoch",
    "title": "Pokemon Glurak ex 199/165 151 Special Illustration Rare Deutsch",
    "description": "Glurak ex aus dem Set 151.",
    "search_query": "Glurak ex 199/165",
    "aspects": [{"name": "Spiel", "value": "Pokémon TCG"}, {"name": "Sprache", "value": "Deutsch"}],
}


def cfg(**kw) -> Config:
    c = Config()
    c.ebay_client_id, c.ebay_client_secret, c.ebay_refresh_token = "id", "secret", "refresh"
    c.ebay_env = "sandbox"
    c.allowed_user_ids = {42}
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_schema_lists_every_property_as_required():
    assert set(CARD_SCHEMA["required"]) == set(CARD_SCHEMA["properties"])
    assert set(CARD) == set(CARD_SCHEMA["properties"])


def test_parse_and_round_price():
    assert parse_price("12,50 €") == 12.5
    assert parse_price("7") == 7.0
    assert parse_price("abc") is None
    assert round_price(3.8, 0.99) == 3.49
    assert round_price(0.2, 0.99) == 0.99
    assert round_price(24.4, 0.99) == 23.99


def test_storage_roundtrip(tmp_path):
    s = Storage(tmp_path)
    draft_id = s.create(1, {"card": CARD, "title": "x", "price": 5.0}, [b"\xff\xd8img"])
    d = s.get(draft_id)
    assert d["status"] == "offen" and d["sku"].startswith("KARTE-")
    assert s.photos(d) == [b"\xff\xd8img"]
    d["price"] = 7.0
    s.update(draft_id, d, status="online")
    assert s.get(draft_id)["price"] == 7.0
    assert [x["id"] for x in s.by_status(1, "online")] == [draft_id]


def test_render_and_description():
    draft = {
        "id": 3, "card": CARD, "title": CARD["title"], "price": 24.99,
        "price_refs": [
            {"source": "eBay (aktuelle Angebote)", "count": 8, "min": 19.0, "median": 27.5, "value": 24.0},
            {"source": "Cardmarket-Trend", "count": 1, "value": 22.1, "raw": 22.1},
        ],
    }
    text = bot.render_draft(draft)
    assert "24,99 €" in text and "Glurak ex" in text and "Cardmarket" in text
    assert "<li><b>Nummer:</b> 199/165</li>" in bot.description_html(draft)


def _mock_ebay(handler) -> EbayClient:
    client = EbayClient(cfg())
    client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def test_pricing_with_mocked_sources():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 7200})
        if "item_summary/search" in request.url.path:
            items = [
                {"title": f"Glurak ex 199/165 151 #{i}", "price": {"value": str(p), "currency": "EUR"}}
                for i, p in enumerate([20, 22, 25, 26, 28, 30, 400])
            ] + [{"title": "PSA 10 Glurak ex 199/165", "price": {"value": "300", "currency": "EUR"}}]
            return httpx.Response(200, json={"itemSummaries": items})
        raise AssertionError(request.url)

    def cm_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.pokemontcg.io"
        return httpx.Response(200, json={"data": [
            {"set": {"id": "sv3pt5", "ptcgoCode": "MEW", "name": "151"},
             "cardmarket": {"prices": {"trendPrice": 24.0}}},
            {"set": {"id": "other", "ptcgoCode": "XXX", "name": "Other"},
             "cardmarket": {"prices": {"trendPrice": 2.0}}},
        ]})

    async def run():
        ebay = _mock_ebay(handler)
        pf = PriceFinder(cfg(), ebay)
        pf.http = httpx.AsyncClient(transport=httpx.MockTransport(cm_handler))
        result = await pf.suggest(CARD, "183454")
        await pf.close()
        await ebay.close()
        return result

    result = asyncio.run(run())
    sources = [r["source"] for r in result["refs"]]
    assert sources[0].startswith("eBay") and sources[1].startswith("Cardmarket")
    ebay_ref = result["refs"][0]
    assert ebay_ref["count"] == 6  # PSA-Angebot und Ausreißer 400 € entfernt
    assert result["refs"][1]["raw"] == 24.0  # nur das passende Set
    assert 19 < result["price"] < 26


def test_create_listing_calls():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        path = request.url.path
        if path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 7200})
        if path.endswith("create_image_from_file"):
            return httpx.Response(201, json={"imageUrl": "https://i.ebayimg.com/x.jpg"})
        if "/sell/account/v1/" in path:
            key = {"fulfillment_policy": "fulfillmentPolicies", "payment_policy": "paymentPolicies",
                   "return_policy": "returnPolicies"}[path.rsplit("/", 1)[1]]
            id_key = {"fulfillmentPolicies": "fulfillmentPolicyId", "paymentPolicies": "paymentPolicyId",
                      "returnPolicies": "returnPolicyId"}[key]
            return httpx.Response(200, json={key: [{id_key: f"{id_key}-1"}]})
        if "/inventory_item/" in path:
            body = json.loads(request.content)
            assert request.headers["Content-Language"] == "de-DE"
            assert body["conditionDescriptors"] == [{"name": "40001", "values": ["400015"]}]
            return httpx.Response(204)
        if path.endswith("/offer"):
            body = json.loads(request.content)
            assert body["pricingSummary"]["price"] == {"value": "4.99", "currency": "EUR"}
            assert body["listingPolicies"]["paymentPolicyId"] == "paymentPolicyId-1"
            return httpx.Response(201, json={"offerId": "O1"})
        if path.endswith("/publish"):
            return httpx.Response(200, json={"listingId": "L1"})
        raise AssertionError(path)

    async def run():
        ebay = _mock_ebay(handler)
        url = await ebay.upload_image(b"img", "a.jpg", "image/jpeg")
        result = await ebay.create_listing(
            sku="S1", title="t", description_html="<p>d</p>", aspects={"Spiel": ["Pokémon TCG"]},
            image_urls=[url], condition="EX", is_sports=False, category_id="183454", price=4.99,
        )
        await ebay.close()
        return result

    assert asyncio.run(run()) == ("O1", "L1")
    assert ("POST", "/sell/inventory/v1/offer/O1/publish") in calls


def test_recognizer_request_shape():
    captured = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=json.dumps(CARD))],
            )

    r = CardRecognizer(cfg())
    r.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))
    r.set_aspects(
        [{"name": "Spiel", "required": True, "selection_only": True, "values": ["Pokémon TCG", "Yu-Gi-Oh! TCG"]}],
        [],
    )
    card = asyncio.run(r.recognize([b"\x89PNG....", b"\xff\xd8...."]))
    assert card["card_name"] == "Glurak ex"
    images = [c for c in captured["messages"][0]["content"] if c["type"] == "image"]
    assert [i["source"]["media_type"] for i in images] == ["image/png", "image/jpeg"]
    assert captured["output_config"]["format"]["schema"] is CARD_SCHEMA
    assert captured["fallbacks"] == "default"
    assert "Spiel (Pflicht) – Werte: Pokémon TCG, Yu-Gi-Oh! TCG" in captured["system"][0]["text"]
