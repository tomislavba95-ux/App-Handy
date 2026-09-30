"""Telegram-Bot: Foto rein -> Karte erkennen -> Preis vorschlagen -> nach Bestätigung auf eBay einstellen."""

import asyncio
import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import config
from .ebay import EbayClient, EbayError
from .pricing import PriceFinder, parse_price
from .recognize import CardRecognizer, image_media_type
from .storage import Storage

log = logging.getLogger(__name__)

CONDITION_NAMES = {
    "NM": "Near Mint (wie neu)",
    "EX": "Excellent (leichte Spuren)",
    "VG": "Very Good (deutliche Spuren)",
    "POOR": "Poor (stark bespielt)",
}
GAME_NAMES = {
    "pokemon": "Pokémon",
    "yugioh": "Yu-Gi-Oh!",
    "fussball": "Fußball",
    "basketball": "Basketball",
    "andere": "Andere",
}
SPORTS = {"fussball", "basketball"}
ALBUM_WAIT_SECONDS = 3
MAX_PARALLEL_RECOGNITIONS = 3

HELP_TEXT = (
    "📸 <b>So geht's:</b>\n"
    "1. Schick mir Fotos einer Karte – am besten Vorder- und Rückseite <b>zusammen</b> "
    "(beide Bilder auswählen und gemeinsam senden).\n"
    "2. Ich erkenne die Karte und schlage einen Preis vor.\n"
    "3. Du bestätigst mit ✅ oder änderst Preis, Titel oder Zustand.\n"
    "4. Erst nach deinem ✅ stelle ich die Karte als Sofort-Kaufen auf eBay ein.\n\n"
    "Befehle:\n"
    "/offen – Karten, die noch auf deine Bestätigung warten\n"
    "/online – Karten, die schon auf eBay sind\n"
    "/hilfe – diese Hilfe"
)


# ---------- Hilfsfunktionen ----------


def _euro(value: float) -> str:
    return f"{value:.2f} €".replace(".", ",")


def render_draft(draft: dict) -> str:
    card = draft["card"]
    e = html.escape
    parts = [p for p in (card["card_name"], card["set_name"], card["card_number"]) if p]
    lines = [
        f"<b>Karte #{draft['id']}</b> · {GAME_NAMES.get(card['game'], card['game'])} "
        f"· Erkennung: {e(card['confidence'])}",
        f"🃏 {e(' – '.join(parts))}",
    ]
    extras = [p for p in (card["language"], card["rarity"], card["variant"], card["year"]) if p]
    if card["game"] in SPORTS:
        extras = [p for p in (card["player_or_character"], card["team"], card["manufacturer"]) if p] + extras
    if extras:
        lines.append(f"ℹ️ {e(' · '.join(extras))}")
    cond = f"📦 Zustand: {CONDITION_NAMES[card['condition']]}"
    if card["condition_notes"]:
        cond += f" – {e(card['condition_notes'])}"
    lines.append(cond)
    lines.append(f"📝 Titel: <i>{e(draft['title'])}</i>")

    if draft.get("price"):
        lines.append(f"\n💶 <b>Preis: {_euro(draft['price'])}</b>" + (" (von dir)" if draft.get("price_manual") else " (Vorschlag)"))
    else:
        lines.append("\n💶 <b>Kein Preis gefunden</b> – bitte mit „Preis ändern“ selbst eingeben.")
    for ref in draft.get("price_refs", []):
        if ref["source"].startswith("eBay"):
            lines.append(
                f"   • {ref['source']}: {ref['count']} Stück, ab {_euro(ref['min'])}, "
                f"Mitte {_euro(ref['median'])}"
            )
        else:
            lines.append(f"   • {e(ref['source'])}: {_euro(ref['raw'])} (Near Mint)")
    if draft.get("price") and draft["price"] < 2:
        lines.append("   ⚠️ Unter 2 € lohnt sich Einzelversand wegen Gebühren kaum.")
    if card["confidence"] == "niedrig":
        lines.append("\n⚠️ Die Erkennung ist unsicher – bitte Angaben genau prüfen!")
    if draft.get("error"):
        lines.append(f"\n❌ Letzter Fehler: {e(draft['error'])}")
    return "\n".join(lines)


def draft_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Auf eBay einstellen", callback_data=f"ok:{draft_id}")],
            [
                InlineKeyboardButton("💶 Preis ändern", callback_data=f"price:{draft_id}"),
                InlineKeyboardButton("📝 Titel ändern", callback_data=f"title:{draft_id}"),
            ],
            [
                InlineKeyboardButton("📦 Zustand ändern", callback_data=f"cond:{draft_id}"),
                InlineKeyboardButton("🗑 Verwerfen", callback_data=f"del:{draft_id}"),
            ],
        ]
    )


def condition_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(name, callback_data=f"setcond:{draft_id}:{code}")]
        for code, name in CONDITION_NAMES.items()
    ]
    rows.append([InlineKeyboardButton("↩️ Zurück", callback_data=f"back:{draft_id}")])
    return InlineKeyboardMarkup(rows)


def description_html(draft: dict) -> str:
    card = draft["card"]
    e = html.escape
    rows = [
        ("Spiel", GAME_NAMES.get(card["game"], card["game"])),
        ("Karte", card["card_name"]),
        ("Spieler/Charakter", card["player_or_character"] if card["game"] in SPORTS else ""),
        ("Team", card["team"]),
        ("Set", card["set_name"]),
        ("Nummer", card["card_number"]),
        ("Seltenheit", card["rarity"]),
        ("Variante", card["variant"]),
        ("Sprache", card["language"]),
        ("Jahr", card["year"]),
        ("Zustand", CONDITION_NAMES[card["condition"]]),
    ]
    table = "".join(f"<li><b>{e(k)}:</b> {e(v)}</li>" for k, v in rows if v)
    notes = f"<p>Zustand: {e(card['condition_notes'])}</p>" if card["condition_notes"] else ""
    return (
        f"<h2>{e(draft['title'])}</h2>"
        f"<p>{e(card['description'])}</p>"
        f"<ul>{table}</ul>{notes}"
        "<p>Die Fotos zeigen genau die Karte, die du erhältst.</p>"
        f"<p>{e(config.shipping_note)}</p>"
        "<p>Privatverkauf.</p>"
    )


# ---------- Zugriffsschutz ----------


async def _allowed(update: Update) -> bool:
    user = update.effective_user
    if user and user.id in config.allowed_user_ids:
        return True
    if update.effective_message:
        await update.effective_message.reply_text(
            f"Deine Telegram-ID ist {user.id if user else '?'}.\n"
            "Trage sie in der Datei .env bei ALLOWED_TELEGRAM_USER_IDS ein und starte den Bot neu. "
            "Danach darfst nur du den Bot benutzen."
        )
    return False


# ---------- Befehle ----------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update):
        return
    text = "👋 Hallo! Ich helfe dir, deine Sammelkarten auf eBay zu verkaufen.\n\n" + HELP_TEXT
    if not config.ebay_can_sell:
        text += "\n\n⚠️ eBay ist noch nicht verbunden – ich kann Karten erkennen und Preise schätzen, aber noch nicht einstellen."
    elif config.is_sandbox:
        text += "\n\n🧪 Testmodus (eBay-Sandbox): Angebote sind nicht echt."
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _allowed(update):
        await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def cmd_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update):
        return
    storage: Storage = context.bot_data["storage"]
    drafts = storage.by_status(update.effective_chat.id, "offen")
    if not drafts:
        await update.message.reply_text("Keine offenen Karten. 🎉")
        return
    for draft in drafts[:20]:
        await update.message.reply_text(
            render_draft(draft), parse_mode=ParseMode.HTML, reply_markup=draft_keyboard(draft["id"])
        )
    if len(drafts) > 20:
        await update.message.reply_text(f"… und {len(drafts) - 20} weitere. Bestätige erst diese.")


async def cmd_online(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update):
        return
    storage: Storage = context.bot_data["storage"]
    drafts = storage.by_status(update.effective_chat.id, "online")
    if not drafts:
        await update.message.reply_text("Noch keine Karte auf eBay eingestellt.")
        return
    lines = [f"<b>{len(drafts)} Karten online:</b>"]
    for d in drafts[-50:]:
        lines.append(f'• <a href="{html.escape(d["listing_url"])}">{html.escape(d["title"])}</a> – {_euro(d["price"])}')
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# ---------- Fotos ----------


async def _download(message: Message) -> bytes | None:
    if message.photo:
        file = await message.photo[-1].get_file()
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        if (message.document.file_size or 0) > 5 * 1024 * 1024:
            await message.reply_text("Das Bild ist größer als 5 MB. Bitte als normales Foto senden.")
            return None
        file = await message.document.get_file()
    else:
        return None
    return bytes(await file.download_as_bytearray())


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update):
        return
    message = update.effective_message
    data = await _download(message)
    if data is None:
        return

    group = message.media_group_id
    if not group:
        await process_card(message, [data], context)
        return

    # Mehrere gemeinsam gesendete Fotos (Album) gehören zu einer Karte
    albums: dict = context.bot_data.setdefault("albums", {})
    if group in albums:
        albums[group].append(data)
        return
    albums[group] = [data]
    await asyncio.sleep(ALBUM_WAIT_SECONDS)
    await process_card(message, albums.pop(group), context)


async def process_card(message: Message, photos: list[bytes], context: ContextTypes.DEFAULT_TYPE) -> None:
    recognizer: CardRecognizer = context.bot_data["recognizer"]
    pricer: PriceFinder = context.bot_data["pricer"]
    storage: Storage = context.bot_data["storage"]
    semaphore: asyncio.Semaphore = context.bot_data["semaphore"]

    status = await message.reply_text("🔍 Erkenne Karte …")
    try:
        async with semaphore:
            card = await recognizer.recognize(photos)
    except Exception as e:  # noqa: BLE001 - Fehler dem Nutzer anzeigen statt abstürzen
        log.exception("Erkennung fehlgeschlagen")
        await status.edit_text(f"❌ Erkennung fehlgeschlagen: {e}")
        return

    if not card["is_card"]:
        await status.edit_text("🤔 Ich sehe auf dem Foto keine Sammelkarte. Bitte nochmal versuchen.")
        return
    if card["is_graded"]:
        await status.edit_text(
            "Das ist eine gegradete Karte (z. B. PSA). Die kann ich noch nicht automatisch einstellen – "
            "bitte bei eBay von Hand verkaufen."
        )
        return

    await status.edit_text("💶 Suche Preise …")
    category_id = config.category_sports if card["game"] in SPORTS else config.category_tcg
    suggestion = await pricer.suggest(card, category_id)
    draft = {
        "card": card,
        "title": card["title"],
        "category_id": category_id,
        "price": suggestion["price"],
        "price_refs": suggestion["refs"],
    }
    draft_id = storage.create(message.chat_id, draft, photos)
    draft = storage.get(draft_id)
    await status.edit_text(render_draft(draft), parse_mode=ParseMode.HTML, reply_markup=draft_keyboard(draft_id))


# ---------- Buttons ----------


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query.from_user or query.from_user.id not in config.allowed_user_ids:
        await query.answer("Nicht erlaubt.")
        return
    await query.answer()
    action, draft_id, *rest = query.data.split(":")
    draft_id = int(draft_id)
    storage: Storage = context.bot_data["storage"]
    draft = storage.get(draft_id)
    if not draft:
        await query.edit_message_text("Diese Karte gibt es nicht mehr.")
        return
    if draft["status"] != "offen":
        await query.edit_message_reply_markup(None)
        return

    if action == "ok":
        busy: set = context.bot_data.setdefault("busy", set())
        if draft_id in busy:
            return
        busy.add(draft_id)
        try:
            await publish(query.message, draft, context)
        finally:
            busy.discard(draft_id)
    elif action in ("price", "title"):
        context.user_data["awaiting"] = (action, draft_id)
        prompt = "Schick mir den neuen Preis in Euro (z. B. 4,99)." if action == "price" else (
            "Schick mir den neuen Titel (höchstens 80 Zeichen)."
        )
        await query.message.reply_text(f"Karte #{draft_id}: {prompt}")
    elif action == "cond":
        await query.edit_message_reply_markup(condition_keyboard(draft_id))
    elif action == "setcond":
        draft["card"]["condition"] = rest[0]
        if not draft.get("price_manual"):
            pricer: PriceFinder = context.bot_data["pricer"]
            suggestion = await pricer.suggest(draft["card"], draft["category_id"])
            draft["price"], draft["price_refs"] = suggestion["price"], suggestion["refs"]
        storage.update(draft_id, draft)
        await query.edit_message_text(
            render_draft(draft), parse_mode=ParseMode.HTML, reply_markup=draft_keyboard(draft_id)
        )
    elif action == "back":
        await query.edit_message_reply_markup(draft_keyboard(draft_id))
    elif action == "del":
        storage.update(draft_id, draft, status="verworfen")
        await query.edit_message_text(f"🗑 Karte #{draft_id} verworfen.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update):
        return
    awaiting = context.user_data.pop("awaiting", None)
    if not awaiting:
        await update.message.reply_text("Schick mir einfach ein Foto einer Karte. /hilfe zeigt alle Befehle.")
        return
    action, draft_id = awaiting
    storage: Storage = context.bot_data["storage"]
    draft = storage.get(draft_id)
    if not draft or draft["status"] != "offen":
        await update.message.reply_text("Diese Karte ist nicht mehr offen.")
        return
    text = update.message.text.strip()
    if action == "price":
        price = parse_price(text)
        if not price or price <= 0:
            context.user_data["awaiting"] = awaiting
            await update.message.reply_text("Das habe ich nicht als Preis verstanden. Bitte z. B. 4,99 schicken.")
            return
        draft["price"], draft["price_manual"] = round(price, 2), True
    else:
        if len(text) > 80:
            context.user_data["awaiting"] = awaiting
            await update.message.reply_text(f"Der Titel hat {len(text)} Zeichen, erlaubt sind 80. Bitte kürzer.")
            return
        draft["title"] = text
    storage.update(draft_id, draft)
    await update.message.reply_text(
        render_draft(draft), parse_mode=ParseMode.HTML, reply_markup=draft_keyboard(draft_id)
    )


# ---------- Einstellen ----------


async def publish(message: Message, draft: dict, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.bot_data["storage"]
    ebay: EbayClient | None = context.bot_data["ebay"]
    draft_id = draft["id"]
    if not config.ebay_can_sell or not ebay:
        await message.reply_text("eBay ist noch nicht verbunden. Siehe Anleitung in der README (Schritt 3).")
        return
    if not draft.get("price"):
        await message.reply_text("Bitte zuerst einen Preis festlegen (💶 Preis ändern).")
        return

    await message.edit_text(render_draft(draft) + "\n\n⏳ Stelle auf eBay ein …", parse_mode=ParseMode.HTML)
    card = draft["card"]
    try:
        if not draft.get("image_urls"):
            urls = []
            for i, img in enumerate(storage.photos(draft)):
                urls.append(await ebay.upload_image(img, f"{draft['sku']}_{i}.jpg", image_media_type(img)))
            draft["image_urls"] = urls
            storage.update(draft_id, draft)
        aspects: dict[str, list[str]] = {}
        for a in card["aspects"]:
            if a["value"]:
                aspects.setdefault(a["name"], []).append(a["value"])
        offer_id, listing_id = await ebay.create_listing(
            sku=draft["sku"],
            title=draft["title"],
            description_html=description_html(draft),
            aspects=aspects,
            image_urls=draft["image_urls"],
            condition=card["condition"],
            is_sports=card["game"] in SPORTS,
            category_id=draft["category_id"],
            price=draft["price"],
            offer_id=draft.get("offer_id"),
        )
    except EbayError as e:
        if e.offer_id:
            draft["offer_id"] = e.offer_id
        draft["error"] = str(e)
        storage.update(draft_id, draft)
        await message.edit_text(
            render_draft(draft) + "\n\nDu kannst Titel/Preis anpassen und es nochmal versuchen.",
            parse_mode=ParseMode.HTML,
            reply_markup=draft_keyboard(draft_id),
        )
        return

    draft.pop("error", None)
    draft.update(offer_id=offer_id, listing_id=listing_id, listing_url=ebay.item_url + listing_id)
    storage.update(draft_id, draft, status="online")
    await message.edit_text(
        f"✅ <b>Karte #{draft_id} ist online!</b>\n{html.escape(draft['title'])}\n"
        f"💶 {_euro(draft['price'])}\n🔗 {html.escape(draft['listing_url'])}",
        parse_mode=ParseMode.HTML,
    )


# ---------- Start ----------


async def _post_init(app: Application) -> None:
    ebay = EbayClient(config) if config.ebay_configured else None
    recognizer = CardRecognizer(config)
    if ebay:
        try:
            recognizer.set_aspects(
                await ebay.item_aspects(config.category_tcg),
                await ebay.item_aspects(config.category_sports),
            )
        except EbayError as e:
            log.warning("Konnte eBay-Artikelmerkmale nicht laden: %s", e)
    app.bot_data.update(
        ebay=ebay,
        recognizer=recognizer,
        pricer=PriceFinder(config, ebay),
        storage=Storage(),
        semaphore=asyncio.Semaphore(MAX_PARALLEL_RECOGNITIONS),
    )


async def _post_shutdown(app: Application) -> None:
    if app.bot_data.get("ebay"):
        await app.bot_data["ebay"].close()
    if app.bot_data.get("pricer"):
        await app.bot_data["pricer"].close()


def build_app() -> Application:
    if not config.telegram_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN fehlt in der .env-Datei (siehe README).")
    app = (
        Application.builder()
        .token(config.telegram_token)
        .concurrent_updates(True)  # nötig, damit Fotos eines Albums parallel ankommen
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("hilfe", cmd_help))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("offen", cmd_open))
    app.add_handler(CommandHandler("online", cmd_online))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_button))
    return app
