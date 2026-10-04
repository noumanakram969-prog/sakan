"""The booking flow, end to end through the engine, with the model stubbed.

The thing being proved: the model never picks a time. It is handed the slots the
garage can genuinely take, and anything else it writes is blocked on the way out.
"""
from datetime import datetime, timedelta

import pytest

from app import booking, engine, slots
from app.db import Booking, SessionLocal, init_db

NOW = datetime(2026, 9, 8, 4, 0)   # Tuesday 08:00 in Dubai
GARAGE_ID = "booktest"
CUSTOMER = "971509990001"

INFO = {
    "name": "Test Auto Repair",
    "timezone": "Asia/Dubai",
    "max_cars_per_hour": 2,
    "address": "Al Quoz 3, Dubai",
    "maps_link": "https://maps.example/test",
    "owner_alert_number": "971500000009",
    "hours": {d: ["08:00", "18:00"] for d in ("mon", "tue", "wed", "thu", "sat", "sun")} | {"fri": None},
}


@pytest.fixture
def garage(sheet):
    return {"id": GARAGE_ID, "prices": sheet, "faq": {}, "info": INFO}


@pytest.fixture(autouse=True)
def clean():
    init_db()
    with SessionLocal() as db:
        db.query(Booking).filter_by(garage_id=GARAGE_ID).delete()
        db.commit()
    yield


def stub(monkeypatch, read, draft="ok"):
    monkeypatch.setattr(engine, "classify", lambda *a, **k: read)
    monkeypatch.setattr(engine, "compose",
                        lambda name, facts, message, history=None, **k:
                        draft(facts) if callable(draft) else draft)


def reply(garage, read, monkeypatch, draft="ok", message="book me in"):
    stub(monkeypatch, read, draft)
    return engine.build_reply(
        garage, message,
        conversation_id=1, customer_number=CUSTOMER, now_utc=NOW,
    )


def full_read(**over):
    """Everything a booking needs, on a day the garage is open."""
    base = {
        "intent": "booking", "language": "en", "confidence": 0.95,
        "service_id": "oil_change", "car_make": "Toyota", "car_model": "Camry",
        "car_year": "2019", "customer_name": "Ahmed",
        "preferred_date": "2026-09-09", "preferred_time": "10:00",
    }
    base.update(over)
    return base


# --- gathering, one question at a time --------------------------------------

@pytest.mark.parametrize("missing,expected", [
    ({"service_id": None}, "which service"),
    ({"car_make": None, "car_model": None, "car_year": None}, "the car"),
])
def test_it_asks_for_exactly_one_missing_thing(garage, monkeypatch, missing, expected):
    seen = {}
    reply(garage, full_read(**missing),
          monkeypatch, lambda f: seen.setdefault("facts", f) or "What is it?")
    facts = seen["facts"]
    assert "Ask only for %s" % expected in facts
    assert facts.count("Ask only for") == 1


def test_the_name_is_never_asked(garage, monkeypatch):
    """We have the WhatsApp number; asking for a name mid-booking caused loops."""
    seen = {}
    # everything present except the name -> it should NOT ask, it should book
    r = reply(garage, full_read(customer_name=None), monkeypatch, "Booked!")
    assert r.booking is not None
    assert r.booking.customer_name == "WhatsApp customer"


def test_it_asks_in_order_service_then_car_then_time(garage, monkeypatch):
    """Everything missing: it starts at the top of the list, not the bottom."""
    seen = {}
    reply(garage, full_read(service_id=None, car_make=None, car_model=None,
                            car_year=None, customer_name=None,
                            preferred_date=None, preferred_time=None),
          monkeypatch, lambda f: seen.setdefault("facts", f) or "?")
    assert "Ask only for which service" in seen["facts"]


def test_what_is_already_known_is_passed_on_so_it_is_not_asked_twice(garage, monkeypatch):
    # Missing the car -> it asks the car via the composer, and the service it
    # already knows is passed along so it is not asked again.
    seen = {}
    reply(garage, full_read(car_make=None, car_model=None, car_year=None),
          monkeypatch, lambda f: seen.setdefault("facts", f) or "?")
    assert "Service: Oil change" in seen["facts"]


# --- slots ------------------------------------------------------------------

def test_only_real_slots_are_offered(garage, monkeypatch):
    # The time picker is tappable buttons, computed from the garage's real hours.
    r = reply(garage, full_read(preferred_date=None, preferred_time=None), monkeypatch)
    assert r.booking is None
    assert r.slot_buttons                                   # offered as buttons
    assert all(":" in title for _, title in r.slot_buttons)  # real times


def test_a_closed_day_is_refused_and_alternatives_offered(garage, monkeypatch):
    """Friday. The garage is shut; it offers other days' times instead of booking."""
    r = reply(garage, full_read(preferred_date="2026-09-11", preferred_time="10:00"), monkeypatch)
    assert r.booking is None
    assert r.slot_buttons                              # alternatives as buttons
    assert "Nothing free on that day" in r.text


def test_a_time_before_opening_is_refused(garage, monkeypatch):
    r = reply(garage, full_read(preferred_time="06:00"), monkeypatch)
    assert r.booking is None
    assert r.slot_buttons                              # offered real times instead
    assert "isn't free" in r.text                      # told the asked time is unavailable


def test_a_full_hour_is_refused(garage, monkeypatch):
    wanted = slots.to_utc(datetime(2026, 9, 9, 10, 0), INFO)
    with SessionLocal() as db:
        for _ in range(2):  # capacity
            db.add(Booking(garage_id=GARAGE_ID, conversation_id=9, customer_name="Other",
                           customer_number="971500000002", car="Patrol", service="Oil change",
                           slot_start=wanted, status="confirmed"))
        db.commit()

    r = reply(garage, full_read(), monkeypatch, "Sorry, that hour is full.")
    assert r.booking is None


# --- confirming -------------------------------------------------------------

def test_a_complete_booking_is_written(garage, monkeypatch):
    r = reply(garage, full_read(), monkeypatch,
              "Booked. Oil change, Toyota Camry 2019, Wed 09 Sep, 10:00.")
    assert r.booking is not None
    with SessionLocal() as db:
        row = db.query(Booking).filter_by(garage_id=GARAGE_ID).one()
        assert row.customer_name == "Ahmed"
        assert row.car == "Toyota Camry 2019"
        assert row.service == "Oil change"
        assert row.customer_number == CUSTOMER
        assert row.status == "confirmed"
        assert slots.describe(row.slot_start, INFO) == "Wed 09 Sep, 10:00"


def test_the_confirmation_carries_the_maps_link(garage, monkeypatch):
    # The confirmation is built in code, not composed — so assert on the reply text.
    r = reply(garage, full_read(), monkeypatch, "unused draft")
    assert r.booking is not None
    assert "https://maps.example/test" in r.text
    assert "Wed 09 Sep, 10:00" in r.text          # the exact tapped time, unreworded


def test_a_slot_the_customer_already_holds_is_not_offered_again(garage, monkeypatch):
    # The loop bug: after booking 10:00, the picker kept OFFERING 10:00, the tap
    # hit the double-book guard, and it looped. The held slot must not reappear.
    assert reply(garage, full_read(preferred_date="2026-09-09", preferred_time="10:00"),
                 monkeypatch, "Booked.").booking is not None
    r = reply(garage, full_read(preferred_date=None, preferred_time=None), monkeypatch)
    titles = [t for _, t in r.slot_buttons]
    assert titles, "should still offer other times"
    assert "Wed 09 Sep, 10:00" not in titles   # the slot they already hold is gone


def test_a_second_service_does_not_reuse_the_first_bookings_time(garage, monkeypatch):
    """After booking at 10:00, a new service must ask for its own time, not silently
    re-book the same slot (the classifier tends to carry the old time)."""
    assert reply(garage, full_read(), monkeypatch, "Booked, Wed 09 Sep, 10:00.").booking
    # same customer, new booking, classifier still reports the old 10:00
    r = reply(garage, full_read(), monkeypatch)
    assert r.booking is None            # did NOT auto-book the same slot again
    assert r.slot_buttons               # asked for a fresh time instead


def test_capacity_is_enforced_across_customers(garage, monkeypatch):
    stub(monkeypatch, full_read(), "Booked, Wed 09 Sep, 10:00.")
    # Two different customers fill the hour (capacity 2); a third is refused.
    for i, num in enumerate(("971500000010", "971500000011")):
        r = engine.build_reply(garage, "book", conversation_id=100 + i,
                               customer_number=num, now_utc=NOW)
        assert r.booking is not None
    r = engine.build_reply(garage, "book", conversation_id=199,
                           customer_number="971500000012", now_utc=NOW)
    assert r.booking is None
    with SessionLocal() as db:
        assert db.query(Booking).filter_by(garage_id=GARAGE_ID).count() == 2


def test_a_slot_taken_between_offer_and_confirm_is_not_overbooked(garage, monkeypatch):
    """The race the availability check on offer cannot cover."""
    wanted = slots.to_utc(datetime(2026, 9, 9, 10, 0), INFO)
    draft = booking.Draft(service_id="oil_change", service_name="Oil change",
                          car="Camry 2019", customer_name="Ahmed", slot_utc=wanted)
    with SessionLocal() as db:
        for _ in range(2):
            db.add(Booking(garage_id=GARAGE_ID, conversation_id=9, customer_name="Other",
                           customer_number="971500000002", car="Patrol", service="Oil change",
                           slot_start=wanted, status="confirmed"))
        db.commit()

    with pytest.raises(booking.SlotGone):
        booking.confirm(GARAGE_ID, INFO, 1, CUSTOMER, draft, NOW)


# --- the guard still applies ------------------------------------------------

def test_the_model_can_never_inject_a_time(garage, monkeypatch):
    """The time picker is code + buttons, so a model 'time' can't reach the customer."""
    r = reply(garage, full_read(preferred_date=None, preferred_time=None),
              monkeypatch, "Sure, come Friday at 06:45.")
    assert not r.is_handoff
    assert "06:45" not in r.text          # the model's draft is ignored entirely
    assert r.slot_buttons                  # real slots offered as buttons instead


def test_a_confirmation_is_deterministic_so_a_model_price_can_never_show(garage, monkeypatch):
    """The confirmation is built in code; the model's draft is ignored entirely,
    so an invented price in that draft can never reach the customer."""
    r = reply(garage, full_read(), monkeypatch, "Booked. That will be AED 180 on the day.")
    assert r.booking is not None          # cleanly confirmed, not a handover
    assert "180" not in r.text            # the model's draft never reaches the customer


# --- off-sheet and no-slot cases -------------------------------------------

def test_booking_an_unlisted_service_hands_over(garage, monkeypatch):
    r = reply(garage, full_read(service_id="gearbox_rebuild"), monkeypatch)
    assert r.is_handoff and "booking off sheet" in r.handoff_reason


def test_a_permanently_closed_garage_hands_over(garage, monkeypatch):
    garage["info"] = dict(INFO, hours={d: None for d in INFO["hours"]})
    r = reply(garage, full_read(preferred_date=None, preferred_time=None), monkeypatch)
    assert r.is_handoff and "no slots available" in r.handoff_reason


def test_without_conversation_context_it_hands_over(garage, monkeypatch):
    stub(monkeypatch, full_read())
    r = engine.build_reply(garage, "book me in", now_utc=NOW)
    assert r.is_handoff


# --- free inspection (symptom path) -----------------------------------------

def test_inspection_draft_needs_only_car_and_slot():
    d = booking.Draft(is_inspection=True, car="Mercedes")
    assert [f for f, _ in d.missing()] == ["slot"]   # no service, no name gate


def test_symptom_with_a_car_offers_inspection_times_as_buttons(garage, monkeypatch):
    # The bug from the field: after the car was given, the bot asked for a time
    # in PLAIN TEXT with nothing to tap. It must offer real slots as buttons.
    read = {"intent": "symptom", "language": "en", "confidence": 0.9,
            "car_make": "Mercedes", "car_year": "2020", "symptom": "engine noise"}
    monkeypatch.setattr(engine, "classify", lambda *a, **k: read)
    monkeypatch.setattr(engine, "compose", lambda *a, **k: "SHOULD NOT COMPOSE")
    r = engine.build_reply(garage, "mercedes 2020",
                           conversation_id=1, customer_number=CUSTOMER, now_utc=NOW)
    assert not r.is_handoff
    assert r.slot_buttons                          # tappable times, not prose
    assert "inspection" in r.text.lower()          # framed as the free inspection
    assert "SHOULD NOT COMPOSE" not in r.text


def test_a_time_pick_after_an_inspection_offer_books_the_inspection(garage, monkeypatch):
    read = {"intent": "booking", "language": "en", "confidence": 0.95,
            "car_make": "Mercedes", "car_year": "2020", "service_id": None,
            "customer_name": None,
            "preferred_date": "2026-09-09", "preferred_time": "10:00"}
    monkeypatch.setattr(engine, "classify", lambda *a, **k: read)
    monkeypatch.setattr(engine, "compose", lambda *a, **k: "ok")
    history = [{"role": "assistant",
                "content": "Let's book you a free inspection. Which time suits?"}]
    r = engine.build_reply(garage, "Wed 09 Sep, 10:00", history,
                           conversation_id=1, customer_number=CUSTOMER, now_utc=NOW)
    assert not r.is_handoff
    assert r.booking is not None                   # completed, did not stall on "service"
    assert "inspection" in (r.booking.service or "").lower()


def test_a_bare_booking_with_no_inspection_context_still_asks_service(garage, monkeypatch):
    # Guard the other side: "book me in", no service, NO inspection offered → we
    # must still ask which service, not silently book an inspection.
    seen = {}
    reply(garage, full_read(service_id=None), monkeypatch,
          lambda f: seen.setdefault("facts", f) or "?")
    assert "Ask only for which service" in seen["facts"]


# --- the owner alert --------------------------------------------------------

def test_the_owner_alert_says_what_he_needs(garage, monkeypatch):
    r = reply(garage, full_read(), monkeypatch, "Booked, Wed 09 Sep, 10:00.")
    alert = booking.owner_alert(r.booking, INFO)
    assert "New booking" in alert
    assert "Ahmed" in alert and "Toyota Camry 2019" in alert
    assert "Wed 09 Sep, 10:00" in alert
    assert CUSTOMER in alert
