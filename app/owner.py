"""Handling messages that came from the owner rather than a customer.

He reaches the bot two ways, and both have to work, because he will use
whichever is in front of him:

* typing in a customer's chat on his own phone - coexistence echoes it to us
* messaging the garage number from his personal phone

A command with no number means "this chat" when he typed it inside one, and
"the whole garage" when he sent it to us directly. That is the reading a person
expects; anything cleverer would need explaining.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from . import commands, conversations, slots, whatsapp
from .db import Booking, Conversation, Handoff, Message, SessionLocal, utcnow

log = logging.getLogger(__name__)


async def handle_command(
    cmd: commands.Command,
    garage_id: str,
    reply_to: str,
    chat_number: str | None,
) -> bool:
    """Run one owner command. Returns False if it could not be acted on."""
    if cmd.action == "help":
        await _say(reply_to, commands.HELP)
        return True

    if cmd.action == "status":
        await _say(reply_to, today_summary(garage_id))
        return True

    target = cmd.number or chat_number

    # No number and not inside a chat: the garage-wide switch.
    if target is None:
        conversations.set_bot_enabled(garage_id, cmd.action == "on")
        await _say(reply_to, "Bot is %s for every chat." % ("on" if cmd.action == "on" else "off"))
        return True

    if cmd.action == "on":
        conversations.release(garage_id, target)
        # A garage-wide off would silently swallow this, so lift it too.
        conversations.set_bot_enabled(garage_id, True)
        await _say(reply_to, "Bot is back on with +%s." % target)
    else:
        conversations.hand_to_owner(garage_id, target, reason="owner asked")
        await _say(reply_to, "Bot will stay out of the chat with +%s." % target)
    return True


async def _say(to: str | None, text: str) -> None:
    """Confirmations are a courtesy. A command still runs if we cannot reply."""
    if not to:
        log.warning("no owner number to confirm to; command still applied")
        return
    try:
        await whatsapp.send_text(to, text)
    except whatsapp.WhatsAppError as exc:
        log.error("could not reply to owner: %s", exc)


def unconfirmed_today(garage_id: str, info: dict, now: datetime | None = None) -> list[Booking]:
    """Cars booked for today that were reminded but never said yes.

    Only the ones already reminded: an empty reply to a reminder is the signal,
    not simply "booked and not confirmed". These are the calls that stop a bay
    from sitting empty this morning.
    """
    now = now or utcnow()
    local_today = slots.to_local(now, info).date()
    with SessionLocal() as db:
        rows = (
            db.query(Booking)
            .filter(
                Booking.garage_id == garage_id,
                Booking.status == "confirmed",
                Booking.confirmed.is_(False),
                Booking.reminder_day_before_sent.is_(True),
                Booking.owner_unconfirmed_alerted.is_(False),
                Booking.slot_start >= now,
                Booking.slot_start <= now + timedelta(days=1),
            )
            .order_by(Booking.slot_start.asc())
            .all()
        )
    return [r for r in rows if slots.to_local(r.slot_start, info).date() == local_today]


def unconfirmed_alert(rows: list[Booking], info: dict) -> str:
    """The owner's morning nudge: who to ring before they no-show."""
    lines = ["%d car(s) booked today haven't confirmed:" % len(rows), ""]
    for r in rows:
        lines.append("• %s — %s, %s (+%s)" % (
            slots.describe(r.slot_start, info), r.car or "car",
            r.service or "service", r.customer_number,
        ))
    lines += ["", "A quick call locks them in or frees the slot."]
    return "\n".join(lines)


def today_summary(garage_id: str, now: datetime | None = None, hours: int = 24) -> str:
    """The 6 pm summary, and what /status prints.

    Deliberately the numbers the owner would ask about, in the order he would
    ask: how much came in, how much of it turned into work, how much needs him.
    """
    now = now or utcnow()
    since = now - timedelta(hours=hours)

    with SessionLocal() as db:
        conversations_started = (
            db.query(Conversation)
            .filter(Conversation.garage_id == garage_id, Conversation.started_at >= since)
            .count()
        )
        after_hours = (
            db.query(Conversation)
            .filter(
                Conversation.garage_id == garage_id,
                Conversation.started_at >= since,
                Conversation.started_outside_hours.is_(True),
            )
            .count()
        )
        bookings = (
            db.query(Booking)
            .filter(
                Booking.garage_id == garage_id,
                Booking.created_at >= since,
                Booking.status != "cancelled",
            )
            .count()
        )
        handoffs = (
            db.query(Handoff)
            .filter(Handoff.garage_id == garage_id, Handoff.created_at >= since)
            .count()
        )
        waiting = (
            db.query(Handoff)
            .filter(Handoff.garage_id == garage_id, Handoff.released_at.is_(None))
            .count()
        )
        answered = (
            db.query(Message)
            .filter(
                Message.garage_id == garage_id,
                Message.created_at >= since,
                Message.sender == "bot",
            )
            .count()
        )

    lines = [
        "Today so far",
        "%d new chats (%d after hours)" % (conversations_started, after_hours),
        "%d replies sent" % answered,
        "%d cars booked" % bookings,
        "%d handed to you" % handoffs,
    ]
    if waiting:
        lines.append("%d still waiting for a call" % waiting)
    return "\n".join(lines)
