"""Storage and the jobs that read it.

Runs on SQLite against the same SQLAlchemy models the deployment uses on
Postgres. The things worth pinning are the ones that bite in production: a
returning buyer being treated as a new one, a redelivered webhook being answered
twice, a lead being pushed at the sales floor on every message, and spend
forgetting itself on restart.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db, store
from app.property.qualify import Lead as LeadState

AGENCY = "demo"


@pytest.fixture
def s(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    db.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", Session)
    monkeypatch.setattr(db, "session", lambda: Session())

    sess = Session()
    store.ensure_agency(sess, AGENCY, "Demo brokerage")
    sess.commit()
    yield sess
    sess.close()


# --- leads ------------------------------------------------------------------

def test_a_returning_buyer_is_the_same_lead(s):
    a = store.get_or_create_lead(s, AGENCY, "971500000001")
    s.commit()
    b = store.get_or_create_lead(s, AGENCY, "971500000001")
    assert a.id == b.id, "asking a returning buyer their budget again loses them"


def test_what_was_learned_on_tuesday_is_still_known_on_friday(s):
    row = store.get_or_create_lead(s, AGENCY, "971500000002")
    store.save_state(s, row, LeadState(beds="2bed", area="jvc", budget_aed=1_500_000))
    s.commit()

    later = store.to_state(store.get_or_create_lead(s, AGENCY, "971500000002"))
    assert later.beds == "2bed" and later.area == "jvc" and later.budget_aed == 1_500_000


def test_the_grade_and_its_reason_are_stored_with_the_lead(s):
    row = store.get_or_create_lead(s, AGENCY, "971500000003")
    store.save_state(s, row, LeadState(
        beds="2bed", area="jvc", budget_aed=1_500_000,
        timeline="immediate", payment="cash"))
    s.commit()
    assert row.grade == "hot"
    assert "cash" in row.grade_reason


def test_two_agencies_never_see_each_others_leads(s):
    store.ensure_agency(s, "other", "Other brokerage")
    a = store.get_or_create_lead(s, AGENCY, "971500000004")
    b = store.get_or_create_lead(s, "other", "971500000004")
    s.commit()
    assert a.id != b.id


def test_a_lead_is_handed_to_the_floor_once_not_on_every_message(s):
    row = store.get_or_create_lead(s, AGENCY, "971500000005")
    s.commit()
    assert store.mark_handover(s, row, "advice") is True
    assert store.mark_handover(s, row, "advice") is False


# --- messages ---------------------------------------------------------------

def test_a_redelivered_webhook_is_recognised(s):
    row = store.get_or_create_lead(s, AGENCY, "971500000006")
    store.record_message(s, row, "in", "hi", wa_message_id="wamid.ABC")
    s.commit()

    assert store.already_seen(s, "wamid.ABC") is True
    assert store.already_seen(s, "wamid.OTHER") is False
    assert store.already_seen(s, None) is False, "no id is not a duplicate"


def test_history_is_oldest_first_and_in_the_shape_the_model_wants(s):
    row = store.get_or_create_lead(s, AGENCY, "971500000007")
    store.record_message(s, row, "in", "first")
    store.record_message(s, row, "out", "second")
    store.record_message(s, row, "in", "third")
    s.commit()

    h = store.history(s, row)
    assert [m["content"] for m in h] == ["first", "second", "third"]
    assert [m["role"] for m in h] == ["user", "assistant", "user"]


def test_history_is_capped_so_a_long_chat_is_not_an_expensive_one(s):
    row = store.get_or_create_lead(s, AGENCY, "971500000008")
    for i in range(30):
        store.record_message(s, row, "in", f"m{i}")
    s.commit()
    assert len(store.history(s, row, turns=8)) == 8


# --- spend ------------------------------------------------------------------

def test_spend_accumulates_per_conversation_per_day(s):
    d = date(2026, 10, 4)
    store.add_spend(s, AGENCY, "971500000009", d, calls=1, input_tokens=100, output_tokens=50, usd=0.01)
    store.add_spend(s, AGENCY, "971500000009", d, calls=1, input_tokens=100, output_tokens=50, usd=0.01)
    s.commit()

    calls, usd = store.spend_today(s, AGENCY, "971500000009", d)
    assert calls == 2 and usd == pytest.approx(0.02)


def test_yesterdays_spend_is_a_different_row(s):
    store.add_spend(s, AGENCY, "x", date(2026, 10, 3), calls=1, input_tokens=1, output_tokens=1, usd=5.0)
    s.commit()
    calls, usd = store.spend_today(s, AGENCY, "x", date(2026, 10, 4))
    assert (calls, usd) == (0, 0.0)


def test_the_month_total_spans_its_days_and_stops_at_the_boundary(s):
    for day in (date(2026, 10, 1), date(2026, 10, 31)):
        store.add_spend(s, AGENCY, "x", day, calls=1, input_tokens=1, output_tokens=1, usd=1.0)
    store.add_spend(s, AGENCY, "x", date(2026, 11, 1), calls=1, input_tokens=1, output_tokens=1, usd=99.0)
    s.commit()

    calls, usd = store.spend_month(s, AGENCY, "2026-10")
    assert calls == 2 and usd == pytest.approx(2.0), "November must not count against October"


# --- what the sales floor asks ----------------------------------------------

def _hot(s, number, *, seen_hours_ago=0, claimed=False):
    row = store.get_or_create_lead(s, AGENCY, number)
    store.save_state(s, row, LeadState(beds="2bed", area="jvc", budget_aed=2_000_000,
                                       timeline="immediate", payment="cash"))
    row.last_seen_at = db.utcnow() - timedelta(hours=seen_hours_ago)
    if claimed:
        row.handed_over_at = db.utcnow()
    s.commit()
    return row


def test_hot_leads_come_back_newest_first(s):
    _hot(s, "971500000010", seen_hours_ago=5)
    _hot(s, "971500000011", seen_hours_ago=1)
    rows = store.hot_leads(s, AGENCY)
    assert rows[0].wa_number.endswith("11")


def test_an_unclaimed_hot_lead_is_chased_and_a_claimed_one_is_not(s):
    _hot(s, "971500000012", seen_hours_ago=3)
    _hot(s, "971500000013", seen_hours_ago=3, claimed=True)

    stale = store.stale_hot_leads(s, AGENCY, older_than_hours=2)
    assert [r.wa_number for r in stale] == ["971500000012"]


def test_a_hot_lead_from_ten_minutes_ago_is_not_chased_yet(s):
    _hot(s, "971500000014", seen_hours_ago=0)
    assert store.stale_hot_leads(s, AGENCY, older_than_hours=2) == []


def test_the_grade_counts_are_what_the_evening_summary_reports(s):
    _hot(s, "971500000015")
    row = store.get_or_create_lead(s, AGENCY, "971500000016")
    store.save_state(s, row, LeadState(beds="2bed", timeline="browsing", budget_aed=900_000))
    s.commit()

    counts = store.counts_by_grade(s, AGENCY)
    assert counts.get("hot") == 1
    assert counts.get("cold") == 1
