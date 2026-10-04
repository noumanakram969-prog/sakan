"""Aftercare: a 'yes' confirms a booking, a 'thanks' earns a review ask.

Both are replies to a message we sent first, so they must never reach the price
engine and must never fire on a fresh question.
"""
from datetime import datetime, timedelta

import pytest

from app import aftercare, slots
from app.db import Booking, Conversation, SessionLocal, init_db, utcnow

GARAGE = "aftertest"
CUSTOMER = "971509990000"

INFO = {
    "name": "Test Auto Repair",
    "timezone": "Asia/Dubai",
    "review_link": "https://g.page/r/testreview",
    "hours": {d: ["08:00", "18:00"] for d in ("mon", "tue", "wed", "thu", "sat", "sun")} | {"fri": None},
}


@pytest.fixture(autouse=True)
def clean():
    init_db()
    with SessionLocal() as db:
        db.query(Booking).filter_by(garage_id=GARAGE).delete()
        db.query(Conversation).filter_by(garage_id=GARAGE).delete()
        db.commit()
    yield


def _now():
    return utcnow().replace(microsecond=0)


def make_booking(*, slot_offset_hours=20, reminded=True, confirmed=False,
                 followup_sent=False, review_sent=False, language="en") -> int:
    with SessionLocal() as db:
        conv = Conversation(garage_id=GARAGE, customer_number=CUSTOMER, language=language)
        db.add(conv)
        db.flush()
        row = Booking(
            garage_id=GARAGE, conversation_id=conv.id, customer_name="Sara",
            customer_number=CUSTOMER, car="Nissan Patrol 2020", service="Oil change",
            slot_start=_now() + timedelta(hours=slot_offset_hours), status="confirmed",
            reminder_day_before_sent=reminded, confirmed=confirmed,
            followup_sent=followup_sent, review_sent=review_sent,
        )
        db.add(row)
        db.commit()
        return row.id


# --- confirmation -----------------------------------------------------------

def test_a_yes_confirms_an_upcoming_reminded_booking():
    bid = make_booking()
    out = aftercare.check(GARAGE, INFO, CUSTOMER, "yes", "en")
    assert out is not None and out.action == "confirmed"
    with SessionLocal() as db:
        assert db.get(Booking, bid).confirmed is True


def test_roman_and_script_affirmatives_confirm():
    for word in ("haan", "ok", "ji", "نعم", "ٹھیک", "👍"):
        make_booking()
        out = aftercare.check(GARAGE, INFO, CUSTOMER, word, "en")
        assert out is not None and out.action == "confirmed", word
        with SessionLocal() as db:
            db.query(Booking).filter_by(garage_id=GARAGE).delete()
            db.query(Conversation).filter_by(garage_id=GARAGE).delete()
            db.commit()


def test_confirmation_reply_is_in_the_customers_language():
    make_booking(language="ar")
    out = aftercare.check(GARAGE, INFO, CUSTOMER, "نعم", "ar")
    assert out is not None and "تم تأكيد" in out.text


def test_a_yes_with_no_reminder_sent_is_left_to_the_engine():
    make_booking(reminded=False)
    assert aftercare.check(GARAGE, INFO, CUSTOMER, "yes", "en") is None


def test_a_real_sentence_is_not_swallowed_as_a_yes():
    make_booking()
    out = aftercare.check(GARAGE, INFO, CUSTOMER,
                          "yes but how much will the brake job cost me?", "en")
    assert out is None


def test_an_already_confirmed_booking_is_not_reconfirmed():
    make_booking(confirmed=True)
    assert aftercare.check(GARAGE, INFO, CUSTOMER, "yes", "en") is None


# --- review -----------------------------------------------------------------

def test_a_happy_reply_after_a_followup_asks_for_a_review():
    bid = make_booking(slot_offset_hours=-48, reminded=False, followup_sent=True)
    out = aftercare.check(GARAGE, INFO, CUSTOMER, "thanks, great service", "en")
    assert out is not None and out.action == "review"
    assert "g.page/r/testreview" in out.text
    with SessionLocal() as db:
        assert db.get(Booking, bid).review_sent is True


def test_no_review_asked_when_the_garage_has_no_review_link():
    make_booking(slot_offset_hours=-48, reminded=False, followup_sent=True)
    info = dict(INFO, review_link="TODO")
    assert aftercare.check(GARAGE, info, CUSTOMER, "shukran", "en") is None


def test_a_review_is_asked_only_once():
    make_booking(slot_offset_hours=-48, reminded=False, followup_sent=True, review_sent=True)
    assert aftercare.check(GARAGE, INFO, CUSTOMER, "thank you", "en") is None


def test_a_happy_reply_with_no_followup_is_left_alone():
    make_booking(slot_offset_hours=-48, reminded=False, followup_sent=False)
    assert aftercare.check(GARAGE, INFO, CUSTOMER, "thanks", "en") is None
