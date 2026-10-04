"""Opening hours and capacity. An offered slot is one the garage can really take."""
from datetime import datetime, timedelta

import pytest

from app import slots
from app.db import Booking, SessionLocal, init_db

# Dubai is UTC+4 all year, so 04:00 UTC is 08:00 local.
NOW = datetime(2026, 9, 8, 4, 0)          # Tuesday 08:00 local
GARAGE = "slottest"

INFO = {
    "timezone": "Asia/Dubai",
    "max_cars_per_hour": 2,
    "hours": {
        "mon": ["08:00", "18:00"],
        "tue": ["08:00", "18:00"],
        "wed": ["08:00", "18:00"],
        "thu": ["08:00", "18:00"],
        "fri": None,                       # closed
        "sat": ["08:00", "18:00"],
        "sun": ["08:00", "18:00"],
    },
}


@pytest.fixture(autouse=True)
def clean_bookings():
    init_db()
    with SessionLocal() as db:
        db.query(Booking).filter_by(garage_id=GARAGE).delete()
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(Booking).filter_by(garage_id=GARAGE).delete()
        db.commit()


def book(slot_utc, status="confirmed"):
    with SessionLocal() as db:
        db.add(Booking(
            garage_id=GARAGE, conversation_id=1, customer_name="X",
            customer_number="971500000000", car="Camry 2019", service="Oil change",
            slot_start=slot_utc, status=status,
        ))
        db.commit()


# --- the timezone boundary --------------------------------------------------

def test_local_and_utc_round_trip():
    local = slots.to_local(NOW, INFO)
    assert local.hour == 8
    assert slots.to_utc(local, INFO) == NOW


def test_open_and_closed():
    assert slots.is_open(INFO, datetime(2026, 9, 8, 9, 0))       # Tuesday morning
    assert not slots.is_open(INFO, datetime(2026, 9, 8, 7, 0))   # before opening
    assert not slots.is_open(INFO, datetime(2026, 9, 8, 18, 0))  # closing time itself
    assert not slots.is_open(INFO, datetime(2026, 9, 11, 10, 0)) # Friday, closed


def test_outside_hours_flag_for_the_report():
    assert not slots.started_outside_hours(INFO, NOW)
    assert slots.started_outside_hours(INFO, NOW - timedelta(hours=3))  # 05:00 local


# --- what may be offered ----------------------------------------------------

def test_offered_slots_are_inside_opening_hours():
    for slot in slots.next_available(GARAGE, INFO, NOW, count=8):
        local = slots.to_local(slot, INFO)
        assert slots.is_open(INFO, local), local


def test_nothing_is_offered_sooner_than_the_lead_time():
    first = slots.next_available(GARAGE, INFO, NOW, count=1)[0]
    assert first >= NOW + timedelta(minutes=slots.LEAD_MINUTES)


def test_friday_is_never_offered():
    for slot in slots.next_available(GARAGE, INFO, NOW, count=20):
        assert slots.to_local(slot, INFO).weekday() != 4


def test_a_full_hour_is_not_offered():
    first = slots.next_available(GARAGE, INFO, NOW, count=1)[0]
    book(first)
    book(first)  # capacity is 2
    assert first not in slots.next_available(GARAGE, INFO, NOW, count=5)


def test_a_half_full_hour_is_still_offered():
    first = slots.next_available(GARAGE, INFO, NOW, count=1)[0]
    book(first)
    assert first in slots.next_available(GARAGE, INFO, NOW, count=5)


def test_a_cancelled_booking_frees_the_slot():
    first = slots.next_available(GARAGE, INFO, NOW, count=1)[0]
    book(first)
    book(first, status="cancelled")
    assert first in slots.next_available(GARAGE, INFO, NOW, count=5)


def test_preferring_a_closed_day_returns_nothing():
    friday = slots.to_local(NOW, INFO).date() + timedelta(days=3)
    assert friday.weekday() == 4
    assert slots.next_available(GARAGE, INFO, NOW, count=3, prefer=friday) == []


def test_preferring_a_past_day_returns_nothing():
    yesterday = slots.to_local(NOW, INFO).date() - timedelta(days=1)
    assert slots.next_available(GARAGE, INFO, NOW, count=3, prefer=yesterday) == []


def test_a_garage_with_no_hours_offers_nothing():
    assert slots.next_available(GARAGE, {"timezone": "Asia/Dubai"}, NOW, count=3) == []


def test_broken_hours_are_treated_as_closed_not_as_all_day():
    bad = dict(INFO, hours={"tue": ["20:00", "08:00"], "wed": ["nonsense"]})
    assert slots.next_available(GARAGE, bad, NOW, count=3) == []


def test_describe_is_stable_and_readable():
    assert slots.describe(datetime(2026, 9, 8, 6, 0), INFO) == "Tue 08 Sep, 10:00"
