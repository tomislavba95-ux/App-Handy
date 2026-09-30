"""Erkennt eine Sammelkarte auf Fotos mit Claude (Bilderkennung)."""

import base64
import json

import anthropic

from .config import Config

GAMES = ["pokemon", "yugioh", "fussball", "basketball", "andere"]
CONDITIONS = ["NM", "EX", "VG", "POOR"]

_str = {"type": "string"}
CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "is_card": {"type": "boolean"},
        "game": {"type": "string", "enum": GAMES},
        "card_name": _str,
        "card_name_en": _str,
        "set_name": _str,
        "set_code": _str,
        "card_number": _str,
        "language": _str,
        "rarity": _str,
        "variant": _str,
        "year": _str,
        "player_or_character": _str,
        "team": _str,
        "manufacturer": _str,
        "is_graded": {"type": "boolean"},
        "condition": {"type": "string", "enum": CONDITIONS},
        "condition_notes": _str,
        "confidence": {"type": "string", "enum": ["hoch", "mittel", "niedrig"]},
        "title": _str,
        "description": _str,
        "search_query": _str,
        "aspects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": _str, "value": _str},
                "required": ["name", "value"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "is_card", "game", "card_name", "card_name_en", "set_name", "set_code", "card_number",
        "language", "rarity", "variant", "year", "player_or_character", "team", "manufacturer",
        "is_graded", "condition", "condition_notes", "confidence", "title", "description",
        "search_query", "aspects",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Du bist Experte für Sammelkarten (Pokémon TCG, Yu-Gi-Oh!, Fußball- und Basketball-Sammelkarten) \
und hilfst einem privaten Verkäufer, einzelne Karten auf eBay.de einzustellen.

Du bekommst ein oder mehrere Fotos derselben Karte (meist Vorder- und Rückseite). Lies alle Angaben, die auf der \
Karte stehen, genau ab: Name, Set/Serie, Setkürzel, Kartennummer (z. B. "025/198" oder "LOB-DE001"), Sprache, \
Seltenheit, Variante (Holo, Reverse Holo, 1. Auflage, Refractor, nummeriert "/99", Autogramm, Rookie usw.), Jahr, \
Hersteller (Panini, Topps, Upper Deck, Konami, The Pokémon Company ...). Rate nichts, was nicht zu erkennen ist: \
lass das Feld dann leer und setze confidence entsprechend niedriger.

Zustand (condition) nach sichtbaren Mängeln an Ecken, Kanten, Oberfläche und Zentrierung:
- NM: praktisch makellos
- EX: leichte Gebrauchsspuren (kleine weiße Kanten, minimale Kratzer)
- VG: deutliche Gebrauchsspuren
- POOR: starke Schäden (Knicke, Risse, Wasserschaden)
Beschreibe sichtbare Mängel kurz in condition_notes. Setze is_graded=true, wenn die Karte in einem Grading-Case \
(PSA, BGS, CGC ...) steckt.

Felder:
- card_name: Name wie auf der Karte gedruckt; card_name_en: offizieller englischer Name (für Preisdatenbanken).
- title: eBay-Titel auf Deutsch, höchstens 80 Zeichen, mit den wichtigsten Suchbegriffen, ohne Zustandsangabe \
(z. B. "Pokemon Glurak ex 199/165 151 Special Illustration Rare Deutsch").
- description: 2–4 sachliche Sätze auf Deutsch über die Karte und ihren Zustand. Keine Übertreibungen.
- search_query: kurze eBay-Suche, die genau diese Karte findet (Name + Nummer/Set, ohne Zustandswörter).
- aspects: eBay-Artikelmerkmale als Name/Wert-Paare. Verwende die unten gelisteten Merkmalsnamen exakt. \
Bei Merkmalen mit vorgegebener Werteliste nimm einen Wert aus der Liste. Fülle alle Pflichtmerkmale aus, \
die sich aus der Karte ergeben; lass Merkmale weg, die du nicht weißt.
- is_card=false, wenn auf dem Foto keine Sammelkarte zu sehen ist.

Artikelmerkmale der eBay-Kategorien:
"""


def _format_aspects(aspects: list[dict]) -> str:
    if not aspects:
        return "  (keine Angaben verfügbar – nutze übliche eBay-Merkmale wie Spiel, Set, Sprache, Kartennummer)\n"
    lines = []
    for a in aspects:
        line = f"  - {a['name']}" + (" (Pflicht)" if a["required"] else "")
        if a["selection_only"] and a["values"]:
            line += f" – Werte: {', '.join(a['values'])}"
        elif a["values"]:
            line += f" – z. B.: {', '.join(a['values'][:10])}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def image_media_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


class CardRecognizer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = anthropic.AsyncAnthropic()
        self.system = SYSTEM_PROMPT

    def set_aspects(self, tcg_aspects: list[dict], sports_aspects: list[dict]) -> None:
        self.system = (
            SYSTEM_PROMPT
            + "\nKategorie Pokémon / Yu-Gi-Oh! (Trading Card Game Karten):\n"
            + _format_aspects(tcg_aspects)
            + "\nKategorie Fußball / Basketball (Sport-Sammelkarten):\n"
            + _format_aspects(sports_aspects)
        )

    async def recognize(self, images: list[bytes]) -> dict:
        content: list[dict] = []
        for img in images:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_media_type(img),
                        "data": base64.standard_b64encode(img).decode(),
                    },
                }
            )
        content.append({"type": "text", "text": "Bitte erkenne diese Karte."})

        response = await self.client.beta.messages.create(
            model=self.cfg.anthropic_model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": CARD_SCHEMA},
            },
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Die KI hat die Anfrage abgelehnt. Bitte ein anderes Foto versuchen.")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Die Antwort der KI war unvollständig. Bitte erneut versuchen.")
        text = next(b.text for b in response.content if b.type == "text")
        card = json.loads(text)
        card["title"] = card["title"][:80]
        return card
