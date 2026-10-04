"""Post-service follow-ups and the service-due nudge.

These go to people who are not expecting them, so the tests here are mostly
about when NOT to send: mid-conversation, twice, to someone who already came
back, or to a garage whose owner said no.
"""
from datetime import datetime, timedelta

import pytest

from app import followups, slots, whatsapp
from app.db import Booking, Conversation, SessionLocal, init_db

GARAGE = "followuptest"

INFO = {
    "name": "Test Auto Repair",
    "timezone": "Asia/Dubai",
    "service_due_months": 6,
    "hours": {d: ["08:00", "18:00"] for d in ("mon", "tue", "wed", "thu", "sat", "sun")} | {"fri": None},
}

# Wednesday 09 Sep 2026, 12:00 local - past SEND_HOUR
NOW = slots.to_utc(datetime(2026, 9, 9, 12, 0), INFO)


@pytest.fixture(autouse=True)
def clean():
    init_db()
    with SessionLocal() as db:
        db.query(Booking).filter_by(garage_id=GARAGE).delete()
        db.query(Conversation).filter_by(garage_id=GARAGE).delete()
        db.commit()
    yield


def make(number="971500000001", days_ago=3, last_message_days_ago=None, **over) -> Booking:
    last_message_days_ago = days_ago if last_message_days_ago is None else last_message_days_ago
    with SessionLocal() as db:
        # One conversation per customer, same as the real thing - a returning
        # customer keeps the chat they already had.
        conv = (
            db.query(Conversation)
            .filter_by(garage_id=GARAGE, customer_number=number)
            .one_or_none()
        )
        if conv is None:
            conv = Conversation(garage_id=GARAGE, customer_number=number, language="en")
            db.add(conv)
        conv.last_message_at = NOW - timedelta(days=last_message_days_ago)
        db.flush()
        fields = dict(
            garage_id=GARAGE, conversation_id=conv.id, customer_name="Ahmed",
            customer_number=number, car="Toyota Camry 2019", service="Oil change",
            slot_start=NOW - timedelta(days=days_ago), status="confirmed",
        )
        fields.update(over)
        row = Booking(**fields)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    async def _send_template(to, name, language, variables=None):
        sent.append({"to": to, "name": name, "language": language, "vars": variables})
        return {"messages": [{"id": "wamid.f"}]}

    monkeypatch.setattr(followups.whatsapp, "send_template", _send_template)
    return sent


# --- post-service -----------------------------------------------------------

def test_two_days_after_the_job_it_is_due():
    make(days_ago=2)
    assert len(followups.due_post_service(GARAGE, INFO, NOW)) == 1


def test_the_day_after_is_too_soon():
    make(days_ago=1)
    assert followups.due_post_service(GARAGE, INFO, NOW) == []


def test_a_month_old_job_is_not_worth_asking_about():
    make(days_ago=40)
    assert followups.due_post_service(GARAGE, INFO, NOW) == []


def test_nobody_is_followed_up_mid_conversation():
    """A "how was it?" arriving while they are complaining reads as not listening."""
    make(days_ago=3, last_message_days_ago=0)
    assert followups.due_post_service(GARAGE, INFO, NOW) == []


def test_a_cancelled_booking_gets_no_follow_up():
    make(days_ago=3, status="cancelled")
    assert followups.due_post_service(GARAGE, INFO, NOW) == []


def test_nothing_goes_out_first_thing_in_the_morning():
    make(days_ago=3)
    early = slots.to_utc(datetime(2026, 9, 9, 7, 0), INFO)
    assert followups.due_post_service(GARAGE, INFO, early) == []


@pytest.mark.asyncio
async def test_it_is_sent_once_and_then_never_again(outbox):
    row = make(days_ago=3)
    assert await followups._send(row, "post_service_followup", INFO, "followup_sent")
    assert outbox[0]["name"] == "post_service_followup"
    assert outbox[0]["vars"] == ["Ahmed", "Oil change", "Test Auto Repair"]
    assert followups.due_post_service(GARAGE, INFO, NOW) == []


# --- service due ------------------------------------------------------------

def test_six_months_on_the_car_is_due():
    make(days_ago=200)
    assert len(followups.due_service_reminder(GARAGE, INFO, NOW)) == 1


def test_three_months_is_too_early():
    make(days_ago=90)
    assert followups.due_service_reminder(GARAGE, INFO, NOW) == []


def test_somebody_who_has_been_back_since_is_not_nudged():
    """The nudge is anchored on their LAST visit, not their first."""
    number = "971500000002"
    make(number=number, days_ago=250)
    make(number=number, days_ago=20, last_message_days_ago=20)
    assert followups.due_service_reminder(GARAGE, INFO, NOW) == []


def test_each_customer_is_nudged_once_not_once_per_old_booking():
    number = "971500000003"
    make(number=number, days_ago=400)
    make(number=number, days_ago=300)
    due = followups.due_service_reminder(GARAGE, INFO, NOW)
    assert len(due) == 1


@pytest.mark.asyncio
async def test_the_nudge_says_how_long_it_has_been(outbox):
    row = make(days_ago=200)
    assert await followups._send(row, "service_due_nudge", INFO, "service_due_sent", months=6)
    assert outbox[0]["vars"] == ["Ahmed", "6", "Oil change", "Test Auto Repair"]


# --- the owner's switches ---------------------------------------------------

@pytest.mark.asyncio
async def test_an_owner_can_turn_follow_ups_off(monkeypatch, outbox):
    make(days_ago=3)
    monkeypatch.setattr(followups.garages, "routable_ids", lambda: [GARAGE])
    monkeypatch.setattr(followups.garages, "load",
                        lambda gid: {"info": dict(INFO, followups_enabled=False)})
    assert await followups.send_due(NOW) == (0, 0)
    assert outbox == []


@pytest.mark.asyncio
async def test_marketing_nudges_can_be_off_while_follow_ups_stay_on(monkeypatch, outbox):
    make(days_ago=3)
    make(number="971500000009", days_ago=250)
    monkeypatch.setattr(followups.garages, "routable_ids", lambda: [GARAGE])
    monkeypatch.setattr(followups.garages, "load",
                        lambda gid: {"info": dict(INFO, service_due_enabled=False)})
    after, nudges = await followups.send_due(NOW)
    assert (after, nudges) == (1, 0)


@pytest.mark.asyncio
async def test_a_failed_send_is_retried_next_time(monkeypatch):
    async def _boom(*a, **k):
        raise whatsapp.WhatsAppError("132001 template does not exist")

    monkeypatch.setattr(followups.whatsapp, "send_template", _boom)
    row = make(days_ago=3)
    assert await followups._send(row, "post_service_followup", INFO, "followup_sent") is False
    assert len(followups.due_post_service(GARAGE, INFO, NOW)) == 1


# --- the migration that lets this ship onto a live database ------------------

def test_the_new_columns_exist_on_an_older_database():
    """init_db adds missing columns rather than asking anyone to delete the file.

    By the time this matters, that file is the pilot report.
    """
    from sqlalchemy import inspect
    from app.db import engine

    columns = {c["name"] for c in inspect(engine).get_columns("bookings")}
    assert {"followup_sent", "service_due_sent"} <= columns
