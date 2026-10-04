"""Booking reminders.

These go outside the 24-hour customer service window, so they must be approved
template messages - see templates/. A template that has not been approved will
fail to send, which is why the template name and its variable order live in the
garage's info.yaml rather than in this file.

Sent once each, tracked by a flag on the booking. A duplicate reminder is worse
than a late one: it reads as a system that does not know what it has done.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from . import garages, slots, whatsapp
from .db import Booking, Conversation, SessionLocal, utcnow

log = logging.getLogger(__name__)

# Local hours at which each reminder goes out.
DAY_BEFORE_HOUR = 18
MORNING_HOUR = 8

DEFAULT_TEMPLATES = {
    "booking_reminder_day_before": {
        "name": "booking_reminder_day_before",
        "vars": ["name", "garage", "time", "service"],
    },
    "booking_reminder_morning": {
        "name": "booking_reminder_morning",
        "vars": ["name", "garage", "time", "maps_link"],
    },
}


def _template(info: dict, key: str) -> dict:
    return ((info.get("templates") or {}).get(key)) or DEFAULT_TEMPLATES[key]


def _variables(spec: dict, row: Booking, info: dict) -> list[str]:
    """Fill the template's variables in the order the template declares them."""
    values = {
        "name": row.customer_name or "",
        "garage": info.get("name") or "",
        "time": slots.describe(row.slot_start, info),
        "service": row.service or "",
        "maps_link": info.get("maps_link") or "",
        "address": info.get("address") or "",
    }
    return [values.get(v, "") for v in (spec.get("vars") or [])]


def _language(conversation_id: int) -> str:
    with SessionLocal() as db:
        conv = db.get(Conversation, conversation_id)
        return (conv.language if conv and conv.language else "en")


def due(garage_id: str, info: dict, now: datetime | None = None) -> list[tuple[Booking, str]]:
    """Which reminders should go out right now, and which kind."""
    now = now or utcnow()
    local_now = slots.to_local(now, info)
    today = local_now.date()
    tomorrow = today + timedelta(days=1)

    out: list[tuple[Booking, str]] = []
    with SessionLocal() as db:
        upcoming = (
            db.query(Booking)
            .filter(
                Booking.garage_id == garage_id,
                Booking.status == "confirmed",
                Booking.slot_start >= now,
                Booking.slot_start <= now + timedelta(days=2),
            )
            .all()
        )

    for row in upcoming:
        slot_local = slots.to_local(row.slot_start, info)

        if (not row.reminder_day_before_sent
                and slot_local.date() == tomorrow
                and local_now.hour >= DAY_BEFORE_HOUR):
            out.append((row, "booking_reminder_day_before"))

        elif (not row.reminder_morning_sent
                and slot_local.date() == today
                and local_now.hour >= MORNING_HOUR):
            out.append((row, "booking_reminder_morning"))

    return out


async def send_due(now: datetime | None = None) -> int:
    """Send whatever is due across every garage. Returns how many went out."""
    sent = 0
    for garage_id in garages.routable_ids():
        try:
            info = garages.load(garage_id).get("info") or {}
        except garages.GarageNotFound:
            continue

        for row, key in due(garage_id, info, now):
            if await _send_one(row, key, info):
                sent += 1
    return sent


async def _send_one(row: Booking, key: str, info: dict) -> bool:
    spec = _template(info, key)
    try:
        await whatsapp.send_template(
            row.customer_number,
            spec["name"],
            _language(row.conversation_id),
            _variables(spec, row, info),
        )
    except whatsapp.WhatsAppError as exc:
        # Almost always an unapproved or renamed template. Leave the flag unset
        # so it retries, and say which one so it can be fixed in Meta.
        log.error("reminder %s failed for booking %s: %s", spec["name"], row.id, exc)
        return False

    field = ("reminder_day_before_sent" if key == "booking_reminder_day_before"
             else "reminder_morning_sent")
    with SessionLocal() as db:
        fresh = db.get(Booking, row.id)
        if fresh is not None:
            setattr(fresh, field, True)
            db.commit()

    log.info("sent %s for booking %s", key, row.id)
    return True
