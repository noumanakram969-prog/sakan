"""Reminders: the right one, once, with the variables the template expects."""
from datetime import datetime, timedelta

import pytest

from app import reminders, slots, whatsapp
from app.db import Booking, Conversation, SessionLocal, init_db

GARAGE = "remindtest"
CUSTOMER = "971509998888"

INFO = {
    "name": "Test Auto Repair",
    "timezone": "Asia/Dubai",
    "maps_link": "https://maps.example/test",
    "hours": {d: ["08:00", "18:00"] for d in ("mon", "tue", "wed", "thu", "sat", "sun")} | {"fri": None},
}

# Wednesday 09 Sep 2026, 10:00 local
SLOT = slots.to_utc(datetime(2026, 9, 9, 10, 0), INFO)


def local(day, hour):
    return slots.to_utc(datetime(2026, 9, day, hour, 0), INFO)


@pytest.fixture(autouse=True)
def clean():
    init_db()
    with SessionLocal() as db:
        db.query(Booking).filter_by(garage_id=GARAGE).delete()
        db.query(Conversation).filter_by(garage_id=GARAGE).delete()
        db.commit()
    yield


def make_booking(language="en") -> Booking:
    with SessionLocal() as db:
        conv = Conversation(garage_id=GARAGE, customer_number=CUSTOMER, language=language)
        db.add(conv)
        db.flush()
        row = Booking(
            garage_id=GARAGE, conversation_id=conv.id, customer_name="Ahmed",
            customer_number=CUSTOMER, car="Toyota Camry 2019", service="Oil change",
            slot_start=SLOT, status="confirmed",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    async def _send_template(to, name, language, variables=None):
        sent.append({"to": to, "name": name, "language": language, "vars": variables})
        return {"messages": [{"id": "wamid.t"}]}

    monkeypatch.setattr(whatsapp, "send_template", _send_template)
    monkeypatch.setattr(reminders.whatsapp, "send_template", _send_template)
    return sent


# --- when each one is due ---------------------------------------------------

def test_the_day_before_reminder_goes_out_the_evening_before():
    make_booking()
    assert reminders.due(GARAGE, INFO, local(8, 18)) != []
    assert reminders.due(GARAGE, INFO, local(8, 18))[0][1] == "booking_reminder_day_before"


def test_nothing_goes_out_too_early_in_the_day_before():
    make_booking()
    assert reminders.due(GARAGE, INFO, local(8, 11)) == []


def test_the_morning_reminder_goes_out_on_the_day():
    row = make_booking()
    with SessionLocal() as db:
        db.get(Booking, row.id).reminder_day_before_sent = True
        db.commit()
    due = reminders.due(GARAGE, INFO, local(9, 8))
    assert due and due[0][1] == "booking_reminder_morning"


def test_nothing_goes_out_after_the_slot_has_passed():
    make_booking()
    assert reminders.due(GARAGE, INFO, local(9, 12)) == []


def test_a_cancelled_booking_gets_no_reminder():
    row = make_booking()
    with SessionLocal() as db:
        db.get(Booking, row.id).status = "cancelled"
        db.commit()
    assert reminders.due(GARAGE, INFO, local(8, 18)) == []


# --- sending ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_template_gets_the_variables_in_declared_order(outbox):
    row = make_booking()
    await reminders._send_one(row, "booking_reminder_day_before", INFO)

    assert outbox[0]["to"] == CUSTOMER
    assert outbox[0]["name"] == "booking_reminder_day_before"
    # name, garage, time, service
    assert outbox[0]["vars"] == ["Ahmed", "Test Auto Repair", "Wed 09 Sep, 10:00", "Oil change"]


@pytest.mark.asyncio
async def test_the_morning_template_carries_the_maps_link(outbox):
    row = make_booking()
    await reminders._send_one(row, "booking_reminder_morning", INFO)
    assert outbox[0]["vars"] == ["Ahmed", "Test Auto Repair", "Wed 09 Sep, 10:00",
                                 "https://maps.example/test"]


@pytest.mark.asyncio
async def test_it_goes_out_in_the_customers_language(outbox):
    row = make_booking(language="ar")
    await reminders._send_one(row, "booking_reminder_day_before", INFO)
    assert outbox[0]["language"] == "ar"


@pytest.mark.asyncio
async def test_a_sent_reminder_is_not_sent_again(outbox):
    row = make_booking()
    await reminders._send_one(row, "booking_reminder_day_before", INFO)
    assert reminders.due(GARAGE, INFO, local(8, 18)) == []


@pytest.mark.asyncio
async def test_a_failed_send_is_retried_not_swallowed(monkeypatch):
    """An unapproved template fails. The flag stays unset so the next tick tries again."""
    async def _boom(*a, **k):
        raise whatsapp.WhatsAppError("132001 template does not exist")

    monkeypatch.setattr(reminders.whatsapp, "send_template", _boom)
    row = make_booking()

    assert await reminders._send_one(row, "booking_reminder_day_before", INFO) is False
    with SessionLocal() as db:
        assert db.get(Booking, row.id).reminder_day_before_sent is False
    assert reminders.due(GARAGE, INFO, local(8, 18)) != []


@pytest.mark.asyncio
async def test_a_garage_can_override_the_template_name(outbox):
    row = make_booking()
    info = dict(INFO, templates={
        "booking_reminder_day_before": {"name": "care_reminder_v2", "vars": ["name", "time"]},
    })
    await reminders._send_one(row, "booking_reminder_day_before", info)
    assert outbox[0]["name"] == "care_reminder_v2"
    assert outbox[0]["vars"] == ["Ahmed", "Wed 09 Sep, 10:00"]
