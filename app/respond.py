"""What happens after a customer message is logged.

Runs as a background task so the webhook can ack Meta inside its timeout. The
webhook never waits on a model call.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from . import aftercare
from . import booking as booking_mod
from . import conversations, engine, garages, slots, whatsapp, wording
from .config import settings
from .db import Conversation, Handoff, Message, SessionLocal, utcnow

log = logging.getLogger(__name__)

SUMMARY_TURNS = 6

# After quoting a price we ask "would you like to book?". If they go quiet this
# long, we offer the times once — a gentle nudge, never repeated.
BOOK_NUDGE_SECONDS = 30
_BOOK_NUDGE = {
    "en": "Here are the next available times if you'd like to book 👇",
    "ar": "هذه أقرب المواعيد المتاحة إن رغبت بالحجز 👇",
    "hi": "Book karna chahein to ye nearest available times hain 👇",
    "ur": "Book karna chahein to ye nearest available times hain 👇",
}


async def handle(conversation_id: int, garage_id: str, inbound_id: int) -> None:
    """Answer one customer message, or hand it to the owner."""
    with SessionLocal() as db:
        conv = db.get(Conversation, conversation_id)
        inbound = db.get(Message, inbound_id)
        if conv is None or inbound is None:
            return

        # Section 6: the owner is on this chat, or the whole bot is off.
        muted = conversations.is_muted(db, conv)
        if muted:
            log.info("not replying to %s: %s", conv.customer_number, muted)
            return

        if _over_daily_cap(db, conversation_id):
            # Somebody in a loop, or a nuisance sender. Every reply past this
            # point is a model call the garage pays for and nobody reads.
            log.warning("reply cap hit for %s, handing to the owner", conv.customer_number)
            over_cap = True
        else:
            over_cap = False

        history = _history(db, conversation_id, exclude_id=inbound_id)
        customer_number = conv.customer_number
        inbound_at = inbound.created_at
        inbound_body = inbound.body
        inbound_type = inbound.msg_type
        known_language = conv.language

    try:
        garage = garages.load(garage_id)
    except garages.GarageNotFound:
        log.error("no knowledge files for garage %r", garage_id)
        return

    if over_cap:
        # Silently to the customer: another message would be the 41st today.
        # Loudly to the owner, who may want to block the number.
        await _hand_over(
            conversation_id, garage, garage_id,
            engine.Reply(text="", intent="other",
                         handoff_reason="reply cap reached (%d today)"
                                        % settings.max_replies_per_day),
            customer_number, history,
        )
        return

    # A "yes" to a reminder, or a "thanks" to a follow-up, is a reply to a
    # message we sent — not a fresh question. Handle it before the engine so it
    # never becomes a price turn or a handover.
    if inbound_type == "text":
        after = aftercare.check(
            garage_id, garage.get("info") or {},
            customer_number, inbound_body, known_language,
        )
        if after is not None:
            try:
                sent = await whatsapp.send_text(customer_number, after.text)
            except whatsapp.WhatsAppError as exc:
                log.error("aftercare send failed to %s: %s", customer_number, exc)
                return
            _record_outbound(
                conversation_id, garage_id,
                engine.Reply(text=after.text, intent=after.action,
                             language=known_language or "en"),
                sent, inbound_at,
            )
            return

    try:
        reply = engine.build_reply(
            garage,
            inbound_body,
            history,
            conversation_id=conversation_id,
            customer_number=customer_number,
            now_utc=utcnow(),
            msg_type=inbound_type,
            language_hint=known_language,
        )
    except Exception:
        # Last resort. Whatever went wrong, a customer who gets no answer at all
        # is worse than one who gets a person - and the owner needs to know.
        log.exception("engine failed for %s", customer_number)
        reply = engine.Reply(
            text=engine.handoff_line(garage, known_language or "en"),
            intent="error",
            language=known_language or "en",
            handoff_reason="engine error - see the log",
        )

    try:
        sent = await _send_reply(customer_number, reply)
    except whatsapp.WhatsAppError as exc:
        log.error("send failed to %s: %s", customer_number, exc)
        return

    _record_outbound(conversation_id, garage_id, reply, sent, inbound_at)

    # After a price quote we asked "would you like to book?". If they go quiet,
    # offer the times once, on a timer — the natural nudge, not a calendar dump.
    if reply.intent == "price" and reply.quote is not None:
        asyncio.create_task(
            _book_nudge_later(conversation_id, garage_id, customer_number,
                              reply.language or "en", utcnow())
        )

    if reply.booking is not None:
        await _tell_owner(garage, booking_mod.owner_alert(reply.booking, garage.get("info") or {}))

    if reply.is_handoff:
        # Include the message that actually triggered the handover, so the owner's
        # summary ends with what the customer needs a call about — not stale chat.
        trail = history + [{"role": "user", "content": inbound_body}] if inbound_body else history
        await _hand_over(conversation_id, garage, garage_id, reply, customer_number, trail)


async def _book_nudge_later(conversation_id, garage_id, customer_number, language, since) -> None:
    """Wait a bit; if the customer hasn't replied to the price, offer times once."""
    await asyncio.sleep(BOOK_NUDGE_SECONDS)
    try:
        with SessionLocal() as db:
            # They replied after the quote → they're engaged, no nudge needed.
            replied = (
                db.query(Message)
                .filter(Message.conversation_id == conversation_id,
                        Message.sender == "customer", Message.created_at > since)
                .first()
            )
            if replied is not None:
                return
            conv = db.get(Conversation, conversation_id)
            if conv is None or conversations.is_muted(db, conv):
                return

        garage = garages.load(garage_id)
        info = garage.get("info") or {}
        options = slots.next_available(garage_id, info, utcnow(), 3)
        if not options:
            return
        buttons = [{"id": "slot|%s" % slots.describe(o, info),
                    "title": slots.describe(o, info)} for o in options]
        text = _BOOK_NUDGE.get(language, _BOOK_NUDGE["en"])
        sent = await whatsapp.send_buttons(customer_number, text, buttons)
        _record_outbound(
            conversation_id, garage_id,
            engine.Reply(text=text, intent="book_nudge", language=language),
            sent, since,
        )
    except garages.GarageNotFound:
        return
    except whatsapp.WhatsAppError as exc:
        log.error("book nudge send failed to %s: %s", customer_number, exc)
    except Exception:
        log.exception("book nudge failed for %s", customer_number)


def _over_daily_cap(db, conversation_id: int) -> bool:
    since = utcnow() - timedelta(hours=24)
    sent = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.sender == "bot",
            Message.created_at >= since,
        )
        .count()
    )
    return sent >= settings.max_replies_per_day


def _history(db, conversation_id: int, exclude_id: int) -> list[dict[str, str]]:
    """Earlier turns only. The message being answered is passed separately."""
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id, Message.id != exclude_id)
        .order_by(Message.id.desc())
        .limit(SUMMARY_TURNS * 2)
        .all()
    )
    return [
        {"role": "user" if m.sender == "customer" else "assistant", "content": m.body}
        for m in reversed(rows)
        if m.body
    ]


# The three quick actions shown after a bare greeting. Static labels — no
# numbers, nothing from the model — so they carry no price-safety risk.
QUICK_MENU = [
    {"id": "menu_book", "title": "Book a car in"},
    {"id": "menu_hours", "title": "Opening hours"},
    {"id": "menu_location", "title": "Our location"},
]


async def _send_reply(to: str, reply):
    """Pick the richest form the reply supports: slot buttons, the quick menu,
    or plain text. Buttons/lists only work inside the 24h window, which a reply
    to an inbound message always is."""
    if reply.slot_buttons:
        buttons = [{"id": "slot|%s" % t, "title": t} for _, t in reply.slot_buttons[:3]]
        return await whatsapp.send_buttons(to, reply.text, buttons)
    if reply.quick_menu:
        return await whatsapp.send_buttons(to, reply.text, QUICK_MENU)
    return await whatsapp.send_text(to, reply.text)


def _record_outbound(conversation_id, garage_id, reply, sent, inbound_at) -> None:
    wa_id = None
    try:
        wa_id = (sent.get("messages") or [{}])[0].get("id")
    except (AttributeError, IndexError):
        pass

    with SessionLocal() as db:
        now = utcnow()

        # The language the customer is actually being answered in. Reminders go
        # out in it later, and it is one of the columns the pilot report needs.
        conv = db.get(Conversation, conversation_id)
        if conv is not None and reply.language:
            conv.language = reply.language

        db.add(
            Message(
                garage_id=garage_id,
                conversation_id=conversation_id,
                wa_message_id=wa_id,
                direction="out",
                sender="bot",
                body=reply.text,
                intent=reply.intent,
                reply_seconds=(now - inbound_at).total_seconds(),
            )
        )
        db.commit()


async def _hand_over(conversation_id, garage, garage_id, reply, customer_number, history) -> None:
    """Rule 3: stop replying, and tell the owner why, with enough to act on."""
    with SessionLocal() as db:
        # The open handoff row is what keeps the bot quiet. No separate timer:
        # one thing to release, one thing to read when asking why it is silent.
        db.add(
            Handoff(
                garage_id=garage_id,
                conversation_id=conversation_id,
                reason=reply.handoff_reason or "unsure",
                summary=_summary(history),
            )
        )
        db.commit()

    await _tell_owner(garage, "\n".join([
        "Customer needs a call: +%s" % customer_number,
        # The internal reason stays in the database for the log and the report.
        # What he reads at nine at night is a sentence.
        wording.plain_reason(reply.handoff_reason),
        "",
        _summary(history) or "(no earlier messages)",
    ]))


async def _tell_owner(garage: dict, text: str) -> None:
    """Owner alerts are best effort. A failed alert never blocks the customer."""
    info = garage.get("info") or {}
    owner = str(info.get("owner_alert_number") or "").strip()
    if not owner or "X" in owner.upper() or owner.upper().startswith("TODO"):
        # info.yaml still has its placeholder in it. Loud, because the owner is
        # not getting his alerts and nothing else would tell him.
        log.warning("no usable owner_alert_number for %s", garage.get("id"))
        return
    try:
        await whatsapp.send_text(owner, text)
    except whatsapp.WhatsAppError as exc:
        log.error("owner alert failed: %s", exc)


def _summary(history: list[dict[str, str]]) -> str:
    """Three lines of chat, newest last. Enough for the owner to pick up the phone."""
    lines = [
        "%s: %s" % ("Them" if h["role"] == "user" else "Bot", h["content"].replace("\n", " ")[:120])
        for h in history[-3:]
    ]
    return "\n".join(lines)
