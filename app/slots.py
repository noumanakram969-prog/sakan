"""When can a car actually come in.

Opening hours and capacity come from the garage's own info.yaml. Nothing here
asks a model anything: an offered slot is a slot the garage can really take, or
it is not offered.

Times in the database are naive UTC, the same convention as every other column.
Times a human sees are the garage's local time. `to_local` and `to_utc` are the
only two places that boundary is crossed.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .db import Booking, SessionLocal

DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

DEFAULT_TZ = "Asia/Dubai"
DEFAULT_CAPACITY = 2
SLOT_MINUTES = 60
SEARCH_DAYS = 14
LEAD_MINUTES = 60  # no slot sooner than this; nobody books a car for 4 minutes' time


def tz(info: dict[str, Any]) -> ZoneInfo:
    return ZoneInfo(info.get("timezone") or DEFAULT_TZ)


def to_local(utc_naive: datetime, info: dict[str, Any]) -> datetime:
    return utc_naive.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz(info)).replace(tzinfo=None)


def to_utc(local_naive: datetime, info: dict[str, Any]) -> datetime:
    return local_naive.replace(tzinfo=tz(info)).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _window(info: dict[str, Any], day: date) -> tuple[time, time] | None:
    """Opening window for one day in local time, or None when closed."""
    hours = info.get("hours") or {}
    raw = hours.get(DAY_KEYS[day.weekday()])
    if not raw:
        return None
    try:
        opens, closes = (time.fromisoformat(str(x)) for x in raw)
    except (TypeError, ValueError):
        return None
    return (opens, closes) if opens < closes else None


def is_open(info: dict[str, Any], local_dt: datetime) -> bool:
    window = _window(info, local_dt.date())
    return bool(window) and window[0] <= local_dt.time() < window[1]


def started_outside_hours(info: dict[str, Any], utc_naive: datetime) -> bool:
    """For the pilot report: how much of this arrived when nobody was there."""
    return not is_open(info, to_local(utc_naive, info))


def _capacity(info: dict[str, Any]) -> int:
    try:
        return max(1, int(info.get("max_cars_per_hour") or DEFAULT_CAPACITY))
    except (TypeError, ValueError):
        return DEFAULT_CAPACITY


def _taken(garage_id: str, slot_utc: datetime) -> int:
    with SessionLocal() as db:
        return (
            db.query(Booking)
            .filter(
                Booking.garage_id == garage_id,
                Booking.slot_start >= slot_utc,
                Booking.slot_start < slot_utc + timedelta(minutes=SLOT_MINUTES),
                Booking.status != "cancelled",
            )
            .count()
        )


def has_room(garage_id: str, info: dict[str, Any], slot_utc: datetime) -> bool:
    return _taken(garage_id, slot_utc) < _capacity(info)


def is_bookable(garage_id: str, info: dict[str, Any], slot_utc: datetime, now_utc: datetime) -> bool:
    """Everything that has to be true before a slot may be confirmed."""
    if slot_utc < now_utc + timedelta(minutes=LEAD_MINUTES):
        return False
    if not is_open(info, to_local(slot_utc, info)):
        return False
    return has_room(garage_id, info, slot_utc)


def _slots_on(info: dict[str, Any], day: date) -> list[datetime]:
    window = _window(info, day)
    if not window:
        return []
    opens, closes = window
    out, cursor = [], datetime.combine(day, opens)
    end = datetime.combine(day, closes)
    while cursor < end:
        out.append(cursor)
        cursor += timedelta(minutes=SLOT_MINUTES)
    return out


def customer_booked_slots(garage_id: str, customer_number: str) -> set[datetime]:
    """The slot times this customer already holds a live booking for. We never
    offer these again — offering a slot the double-book guard will then reject is
    exactly what made the time picker loop forever."""
    if not customer_number:
        return set()
    with SessionLocal() as db:
        rows = (
            db.query(Booking.slot_start)
            .filter(
                Booking.garage_id == garage_id,
                Booking.customer_number == customer_number,
                Booking.status != "cancelled",
            )
            .all()
        )
    return {r[0] for r in rows}


def next_available(
    garage_id: str,
    info: dict[str, Any],
    now_utc: datetime,
    count: int = 3,
    prefer: date | None = None,
    exclude_customer: str | None = None,
) -> list[datetime]:
    """The next few slots the garage can genuinely take, in UTC.

    `prefer` restricts the search to one day, which is how "can I come Saturday?"
    is answered honestly: either that day has room or it does not.

    `exclude_customer` drops slots that customer already holds — so a tapped
    button is always bookable and the picker can never loop.
    """
    start_local = to_local(now_utc, info).date()
    days = [prefer] if prefer else [start_local + timedelta(days=i) for i in range(SEARCH_DAYS)]
    theirs = customer_booked_slots(garage_id, exclude_customer) if exclude_customer else set()

    found: list[datetime] = []
    for day in days:
        if day is None or day < start_local:
            continue
        for local_slot in _slots_on(info, day):
            slot_utc = to_utc(local_slot, info)
            if slot_utc in theirs:
                continue
            if is_bookable(garage_id, info, slot_utc, now_utc):
                found.append(slot_utc)
                if len(found) >= count:
                    return found
    return found


def describe(slot_utc: datetime, info: dict[str, Any]) -> str:
    """How a slot is written to a customer. Also what the outbound guard allows."""
    local = to_local(slot_utc, info)
    return local.strftime("%a %d %b, %H:%M")
