"""Turning a conversation into a row in `bookings`.

What a booking needs before it can be confirmed, in the order the bot asks for
it. One question at a time - the order here is the order the customer is asked.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from . import slots
from .db import Booking, SessionLocal

log = logging.getLogger(__name__)

# field, what to call it when asking. The NAME is deliberately not here: we have
# the customer's WhatsApp number to reach them, and asking for a name mid-booking
# made the flow loop (a one-word reply like "roman" wasn't reliably read back as
# the name). Gather only what a booking truly needs: service, car, time.
REQUIRED = (
    ("service", "which service they want"),
    ("car", "the car - make, model and year"),
    ("slot", "the day and time that suits them"),
)


@dataclass
class Draft:
    """What has been gathered so far. Missing pieces are what to ask about next."""
    service_id: str | None = None
    service_name: str | None = None
    car: str | None = None
    customer_name: str | None = None
    slot_utc: datetime | None = None
    preferred_day: date | None = None
    # A free inspection (the symptom path, or a "book me in" with no named
    # service). There is no service to pick and we don't gate on a name — the
    # car and a time are enough, so the customer reaches the slot picker at once.
    is_inspection: bool = False

    def missing(self) -> list[tuple[str, str]]:
        have = {
            "service": self.service_id or self.is_inspection,
            "car": self.car,
            "slot": self.slot_utc,
        }
        return [(f, label) for f, label in REQUIRED if not have[f]]

    @property
    def complete(self) -> bool:
        return not self.missing()


class SlotGone(Exception):
    """Taken between offering it and confirming it. Offer another, never overbook."""


def confirm(
    garage_id: str,
    info: dict[str, Any],
    conversation_id: int,
    customer_number: str,
    draft: Draft,
    now_utc: datetime,
) -> Booking:
    """Write the booking, re-checking availability first.

    The check on offer is not enough: two customers can be offered the same slot
    seconds apart. This is the one that counts.
    """
    if not draft.complete:
        raise ValueError("incomplete draft: %s" % [f for f, _ in draft.missing()])

    if not slots.is_bookable(garage_id, info, draft.slot_utc, now_utc):
        raise SlotGone(slots.describe(draft.slot_utc, info))

    with SessionLocal() as db:
        row = Booking(
            garage_id=garage_id,
            conversation_id=conversation_id,
            customer_name=draft.customer_name or "WhatsApp customer",
            customer_number=customer_number,
            car=draft.car,
            service=draft.service_name or draft.service_id,
            slot_start=draft.slot_utc,
            status="confirmed",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

    log.info("booked %s for %s at %s", row.service, row.customer_name,
             slots.describe(row.slot_start, info))
    return row


def confirmation_facts(row: Booking, info: dict[str, Any]) -> list[str]:
    """What the composer may say about a confirmed booking, and nothing more."""
    facts = [
        "The booking is confirmed. Tell them so, briefly.",
        "Name: %s" % row.customer_name,
        "Car: %s" % row.car,
        "Service: %s" % row.service,
        "When: %s" % slots.describe(row.slot_start, info),
    ]
    if info.get("maps_link"):
        facts.append("Send this maps link: %s" % info["maps_link"])
    if info.get("address"):
        facts.append("Address: %s" % info["address"])
    return facts


def owner_alert(row: Booking, info: dict[str, Any]) -> str:
    return "\n".join([
        "New booking",
        "%s - %s" % (row.customer_name, row.car),
        "%s at %s" % (row.service, slots.describe(row.slot_start, info)),
        "+%s" % row.customer_number,
    ])
