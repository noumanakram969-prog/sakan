"""The two messages that go out after a car has left.

This is the part a garage renews for. A chatbot that answers questions is
pleasant; a system that brings thirty cars a month back through the door is
something he can point at. Cancelling then means switching off the thing that
refills his bay, and that is a different conversation from "the bot is nice".

Both are template messages, because they land long outside the 24-hour window.

Two rules that keep this from becoming spam, which would cost the garage more
than it earns:

* Never message someone who is mid-conversation. A "how was it?" arriving while
  they are complaining about the work reads as a machine that is not listening.
* Once each, ever, per booking. The flags live on the booking row.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from . import garages, slots, whatsapp
from .db import Booking, Conversation, SessionLocal, utcnow

log = logging.getLogger(__name__)

POST_SERVICE_DAYS = 2          # after the appointment
DEFAULT_SERVICE_DUE_MONTHS = 6
QUIET_HOURS = 48               # do not follow up on an active conversation
SEND_HOUR = 11                 # local; mid-morning, not first thing

DEFAULT_TEMPLATES = {
    "post_service_followup": {
        "name": "post_service_followup",
        "vars": ["name", "service", "garage"],
    },
    "service_due_nudge": {
        "name": "service_due_nudge",
        "vars": ["name", "months", "service", "garage"],
    },
}


def _template(info: dict, key: str) -> dict:
    return ((info.get("templates") or {}).get(key)) or DEFAULT_TEMPLATES[key]


def _months(info: dict) -> int:
    try:
        return max(1, int(info.get("service_due_months") or DEFAULT_SERVICE_DUE_MONTHS))
    except (TypeError, ValueError):
        return DEFAULT_SERVICE_DUE_MONTHS


def _recently_active(db, conversation_id: int, now: datetime) -> bool:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        return True  # no conversation to message into; skip rather than guess
    return conv.last_message_at > now - timedelta(hours=QUIET_HOURS)


def due_post_service(garage_id: str, info: dict, now: datetime | None = None) -> list[Booking]:
    """Two days after the appointment: how did it go?"""
    now = now or utcnow()
    if slots.to_local(now, info).hour < SEND_HOUR:
        return []

    cutoff = now - timedelta(days=POST_SERVICE_DAYS)
    with SessionLocal() as db:
        rows = (
            db.query(Booking)
            .filter(
                Booking.garage_id == garage_id,
                Booking.status != "cancelled",
                Booking.followup_sent.is_(False),
                Booking.slot_start <= cutoff,
                # A month-old job is not worth asking about any more.
                Booking.slot_start >= cutoff - timedelta(days=14),
            )
            .all()
        )
        return [r for r in rows if not _recently_active(db, r.conversation_id, now)]


def due_service_reminder(garage_id: str, info: dict, now: datetime | None = None) -> list[Booking]:
    """N months on: their car is due again.

    Anchored on the most recent booking for that number, so somebody who came
    back last week is not nudged about a visit from six months ago.
    """
    now = now or utcnow()
    if slots.to_local(now, info).hour < SEND_HOUR:
        return []

    months = _months(info)
    cutoff = now - timedelta(days=months * 30)

    with SessionLocal() as db:
        rows = (
            db.query(Booking)
            .filter(
                Booking.garage_id == garage_id,
                Booking.status != "cancelled",
                Booking.service_due_sent.is_(False),
                Booking.slot_start <= cutoff,
            )
            .order_by(Booking.slot_start.desc())
            .all()
        )

        out, seen = [], set()
        for row in rows:
            if row.customer_number in seen:
                continue
            seen.add(row.customer_number)

            latest = (
                db.query(Booking)
                .filter(
                    Booking.garage_id == garage_id,
                    Booking.customer_number == row.customer_number,
                    Booking.status != "cancelled",
                )
                .order_by(Booking.slot_start.desc())
                .first()
            )
            if latest is None or latest.id != row.id:
                continue  # they have been back since
            if _recently_active(db, row.conversation_id, now):
                continue
            out.append(row)

        return out


def _variables(spec: dict, row: Booking, info: dict, months: int) -> list[str]:
    values = {
        "name": row.customer_name or "",
        "service": row.service or "",
        "garage": info.get("name") or "",
        "months": str(months),
        "car": row.car or "",
    }
    return [values.get(v, "") for v in (spec.get("vars") or [])]


def _language(conversation_id: int) -> str:
    with SessionLocal() as db:
        conv = db.get(Conversation, conversation_id)
        return conv.language if conv and conv.language else "en"


async def _send(row: Booking, key: str, info: dict, flag: str, months: int = 0) -> bool:
    spec = _template(info, key)
    try:
        await whatsapp.send_template(
            row.customer_number,
            spec["name"],
            _language(row.conversation_id),
            _variables(spec, row, info, months),
        )
    except whatsapp.WhatsAppError as exc:
        log.error("%s failed for booking %s: %s", spec["name"], row.id, exc)
        return False

    with SessionLocal() as db:
        fresh = db.get(Booking, row.id)
        if fresh is not None:
            setattr(fresh, flag, True)
            db.commit()

    log.info("sent %s for booking %s", key, row.id)
    return True


async def send_due(now: datetime | None = None) -> tuple[int, int]:
    """Returns (post-service sent, service-due sent)."""
    followups = nudges = 0

    for garage_id in garages.routable_ids():
        try:
            info = garages.load(garage_id).get("info") or {}
        except garages.GarageNotFound:
            continue

        if not info.get("followups_enabled", True):
            continue

        for row in due_post_service(garage_id, info, now):
            if await _send(row, "post_service_followup", info, "followup_sent"):
                followups += 1

        # Marketing category. The garage should have told its customers it will
        # do this; the switch above is how an owner says no.
        if info.get("service_due_enabled", True):
            months = _months(info)
            for row in due_service_reminder(garage_id, info, now):
                if await _send(row, "service_due_nudge", info, "service_due_sent", months):
                    nudges += 1

    return followups, nudges
