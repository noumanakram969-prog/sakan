"""Onboarding nudges: finish-setup reminder and the 'all set' welcome.

Each fires once. Sending is mocked — we test who gets messaged and that flags
flip so nobody is pestered twice.
"""
import shutil
from datetime import timedelta

import pytest

from app import garages, nudges, onboard, whatsapp
from app.db import Owner, SessionLocal, init_db, utcnow

_CREATED: list[str] = []


@pytest.fixture(autouse=True)
def clean():
    init_db()
    with SessionLocal() as db:
        db.query(Owner).delete()
        db.commit()
    yield
    for gid in _CREATED:
        shutil.rmtree(onboard.GARAGES_DIR / gid, ignore_errors=True)
        garages._cache.pop(gid, None)
    _CREATED.clear()


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    async def _send_template(to, name, language, variables=None):
        sent.append({"to": to, "name": name, "vars": variables})
        return {"messages": [{"id": "wamid.x"}]}

    monkeypatch.setattr(whatsapp, "send_template", _send_template)
    monkeypatch.setattr(nudges.whatsapp, "send_template", _send_template)
    return sent


def _make(gid, *, number, prices_filled, created_ago_hours=0, welcomed=False, nudged=False):
    folder = onboard.GARAGES_DIR / gid
    _CREATED.append(gid)
    onboard._write(gid, "info", {"id": gid, "name": gid.title(), "pending": True,
                                 "owner_alert_number": number})
    price = "180" if prices_filled else "TODO"
    onboard._write(gid, "prices", {"currency": "AED", "services": [
        {"id": "oil_change", "name": {"en": "Oil"}, "prices": {"sedan": price}}]})
    onboard._write(gid, "faq", {"faqs": []})
    garages._cache.pop(gid, None)
    with SessionLocal() as db:
        db.add(Owner(garage_id=gid, number=number, password_hash="x",
                     created_at=utcnow() - timedelta(hours=created_ago_hours),
                     welcomed=welcomed, setup_nudged=nudged))
        db.commit()


# --- setup reminder ---------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_with_no_prices_after_a_day_gets_a_reminder(outbox):
    _make("nudge-a", number="971500000001", prices_filled=False, created_ago_hours=30)
    n = await nudges.send_setup_reminders()
    assert n == 1 and outbox[0]["name"] == "onboarding_reminder"
    with SessionLocal() as db:
        assert db.query(Owner).filter_by(garage_id="nudge-a").first().setup_nudged is True


@pytest.mark.asyncio
async def test_a_fresh_signup_is_not_nudged_yet(outbox):
    _make("nudge-b", number="971500000002", prices_filled=False, created_ago_hours=2)
    assert await nudges.send_setup_reminders() == 0


@pytest.mark.asyncio
async def test_an_owner_who_started_their_prices_is_not_nudged(outbox):
    _make("nudge-c", number="971500000003", prices_filled=True, created_ago_hours=30)
    assert await nudges.send_setup_reminders() == 0


@pytest.mark.asyncio
async def test_the_reminder_is_sent_only_once(outbox):
    _make("nudge-d", number="971500000004", prices_filled=False, created_ago_hours=30)
    await nudges.send_setup_reminders()
    assert await nudges.send_setup_reminders() == 0


# --- welcome ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_completing_setup_sends_the_welcome_once(outbox):
    _make("welcome-a", number="971500000010", prices_filled=True)
    await nudges.maybe_welcome("welcome-a")
    assert outbox and outbox[0]["name"] == "onboarding_welcome"
    with SessionLocal() as db:
        assert db.query(Owner).filter_by(garage_id="welcome-a").first().welcomed is True
    # calling again does nothing
    outbox.clear()
    await nudges.maybe_welcome("welcome-a")
    assert outbox == []


@pytest.mark.asyncio
async def test_no_welcome_while_setup_is_incomplete(outbox):
    _make("welcome-b", number="971500000011", prices_filled=False)
    await nudges.maybe_welcome("welcome-b")
    assert outbox == []
