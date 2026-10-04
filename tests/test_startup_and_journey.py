"""Does the service actually start, and does one customer get all the way through?

291 tests and nothing had ever run the application's own startup, or followed a
single customer from "how much?" to a reminder. Both are the kind of thing that
works in pieces and fails joined up.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import booking, engine, followups, reminders, scheduler, slots, whatsapp
from app.config import settings
from app.db import Booking, Conversation, Message, SessionLocal, init_db
from app.main import app

GARAGE = "demo"
CUSTOMER = "971509991234"


# --- the service starts -----------------------------------------------------

def test_the_application_starts_and_serves(monkeypatch):
    """Runs the real lifespan: tables created, scheduler up, health answering.

    Every other test skips this by using TestClient without a context manager.
    """
    monkeypatch.setattr(settings, "enable_scheduler", True)
    scheduler.stop()  # a previous test may have left one running

    with TestClient(app) as started:
        r = started.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        assert scheduler._scheduler is not None
        jobs = {j.id for j in scheduler._scheduler.get_jobs()}
        assert jobs == {"reminders", "release", "summary", "followups", "unconfirmed",
                        "setup_reminders"}

    scheduler.stop()


def test_it_also_starts_with_the_scheduler_off(monkeypatch):
    """How it runs in a shell, and in tests."""
    monkeypatch.setattr(settings, "enable_scheduler", False)
    scheduler.stop()
    with TestClient(app) as started:
        assert started.get("/health").status_code == 200
    assert scheduler._scheduler is None


def test_the_webhook_verification_handshake_works_on_a_started_app(monkeypatch):
    monkeypatch.setattr(settings, "enable_scheduler", False)
    scheduler.stop()
    with TestClient(app) as started:
        r = started.get("/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.meta_verify_token,
            "hub.challenge": "99999",
        })
        assert r.status_code == 200 and r.text == "99999"


# --- one customer, all the way through --------------------------------------

@pytest.fixture(autouse=True)
def clean():
    init_db()
    with SessionLocal() as db:
        for conv in db.query(Conversation).filter_by(customer_number=CUSTOMER).all():
            db.query(Message).filter_by(conversation_id=conv.id).delete()
            db.query(Booking).filter_by(conversation_id=conv.id).delete()
            db.delete(conv)
        db.commit()
    yield


@pytest.fixture
def demo_garage():
    from app import garages
    return garages.load(GARAGE)


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    async def _send_template(to, name, language, variables=None):
        sent.append({"to": to, "name": name, "vars": variables})
        return {"messages": [{"id": "wamid.j"}]}

    monkeypatch.setattr(whatsapp, "send_template", _send_template)
    monkeypatch.setattr(reminders.whatsapp, "send_template", _send_template)
    monkeypatch.setattr(followups.whatsapp, "send_template", _send_template)
    return sent


def model(monkeypatch, read, draft):
    monkeypatch.setattr(engine, "classify", lambda *a, **k: read)
    monkeypatch.setattr(engine, "compose",
                        lambda name, facts, message, history=None, **k:
                        draft(facts) if callable(draft) else draft)


@pytest.mark.asyncio
async def test_a_customer_goes_from_a_price_question_to_a_reminder(
    monkeypatch, demo_garage, outbox
):
    """Ask a price, book the car in, get reminded, get followed up.

    Every step is a piece that has its own tests. This is the only place that
    checks they join up, on the real demo sheet, with real opening hours.
    """
    info = demo_garage["info"]
    # Tuesday 08 Sep 2026, 09:00 in Dubai - the garage is open
    now = slots.to_utc(datetime(2026, 9, 8, 9, 0), info)

    with SessionLocal() as db:
        conv = Conversation(garage_id=GARAGE, customer_number=CUSTOMER, language="en")
        db.add(conv)
        db.commit()
        conversation_id = conv.id

    # 1. "how much for an oil change on my camry?" ---------------------------
    model(monkeypatch,
          {"intent": "price", "language": "en", "service_id": "oil_change",
           "car_category": "sedan", "car_make": "Toyota", "car_model": "Camry",
           "car_year": "2019", "confidence": 0.95},
          "Oil change, Toyota Camry 2019 - AED 180. When suits you?")

    priced = engine.build_reply(
        demo_garage, "how much for an oil change on my camry 2019?",
        conversation_id=conversation_id, customer_number=CUSTOMER, now_utc=now,
    )
    assert not priced.is_handoff
    assert priced.quote.text == "180", "the demo sheet says 180"
    assert "180" in priced.text

    # 2. "book me in tomorrow at 10" ----------------------------------------
    model(monkeypatch,
          {"intent": "booking", "language": "en", "service_id": "oil_change",
           "car_make": "Toyota", "car_model": "Camry", "car_year": "2019",
           "customer_name": "Ahmed", "preferred_date": "2026-09-09",
           "preferred_time": "10:00", "confidence": 0.95},
          "Booked, Ahmed. Oil change, Wed 09 Sep, 10:00.")

    booked = engine.build_reply(
        demo_garage, "yes book me tomorrow 10am, name is Ahmed",
        conversation_id=conversation_id, customer_number=CUSTOMER, now_utc=now,
    )
    assert booked.booking is not None
    row_id = booked.booking.id
    assert slots.describe(booked.booking.slot_start, info) == "Wed 09 Sep, 10:00"

    # the owner is told, with what he needs to act on
    alert = booking.owner_alert(booked.booking, info)
    assert "Ahmed" in alert and "Wed 09 Sep, 10:00" in alert and CUSTOMER in alert

    # 3. the evening before, a reminder --------------------------------------
    evening = slots.to_utc(datetime(2026, 9, 8, 18, 30), info)
    due = reminders.due(GARAGE, info, evening)
    assert [(r.id, k) for r, k in due] == [(row_id, "booking_reminder_day_before")]
    assert await reminders._send_one(booked.booking, "booking_reminder_day_before", info)
    assert outbox[-1]["to"] == CUSTOMER
    assert "Wed 09 Sep, 10:00" in outbox[-1]["vars"]

    # 4. on the morning, another --------------------------------------------
    morning = slots.to_utc(datetime(2026, 9, 9, 8, 30), info)
    due = reminders.due(GARAGE, info, morning)
    assert [k for _, k in due] == ["booking_reminder_morning"]

    with SessionLocal() as db:
        db.get(Booking, row_id).reminder_morning_sent = True
        db.commit()

    # 5. two days later, how was it? ----------------------------------------
    after = slots.to_utc(datetime(2026, 9, 11, 12, 0), info)
    with SessionLocal() as db:
        # they have not written since the booking
        db.get(Conversation, conversation_id).last_message_at = now
        db.commit()

    assert [r.id for r in followups.due_post_service(GARAGE, info, after)] == [row_id]

    # 6. and nothing goes out twice -----------------------------------------
    with SessionLocal() as db:
        db.get(Booking, row_id).followup_sent = True
        db.commit()
    assert followups.due_post_service(GARAGE, info, after) == []

    # 7. six months on, their car is due -------------------------------------
    later = slots.to_utc(datetime(2027, 4, 1, 12, 0), info)
    assert [r.id for r in followups.due_service_reminder(GARAGE, info, later)] == [row_id]


@pytest.mark.asyncio
async def test_the_same_journey_refuses_a_slot_the_garage_cannot_take(
    monkeypatch, demo_garage
):
    """Friday afternoon only. The demo garage opens at 14:00 that day."""
    info = demo_garage["info"]
    now = slots.to_utc(datetime(2026, 9, 8, 9, 0), info)

    with SessionLocal() as db:
        conv = Conversation(garage_id=GARAGE, customer_number=CUSTOMER, language="en")
        db.add(conv)
        db.commit()
        conversation_id = conv.id

    model(monkeypatch,
          {"intent": "booking", "language": "en", "service_id": "oil_change",
           "car_make": "Toyota", "car_model": "Camry", "car_year": "2019",
           "customer_name": "Ahmed", "preferred_date": "2026-09-11",
           "preferred_time": "09:00", "confidence": 0.95},
          "Sorry, how about these?")

    reply = engine.build_reply(
        demo_garage, "friday 9am please",
        conversation_id=conversation_id, customer_number=CUSTOMER, now_utc=now,
    )
    assert reply.booking is None
    assert "isn't free" in reply.text
    # and it offered real Friday slots as buttons, because the garage opens at 14:00
    assert "Fri 11 Sep, 14:00" in [t for _, t in reply.slot_buttons]
