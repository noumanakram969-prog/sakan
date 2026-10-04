"""The pilot report and the admin page.

The report is the thing garage number two gets shown, so a wrong number here is
expensive in a way a wrong number elsewhere is not.
"""
import base64
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import report
from app.cli import main as cli_main
from app.db import Booking, Conversation, Handoff, Message, SessionLocal, init_db
from app.main import app

GARAGE = "reporttest"
START = datetime(2026, 9, 1)
END = datetime(2026, 10, 1)

from app.admin import SESSION_COOKIE, _session_value  # noqa: E402

client = TestClient(app)
# Admin auth is cookie-only now; a Cookie header authenticates the request.
AUTH = {"Cookie": "%s=%s" % (SESSION_COOKIE, _session_value())}


@pytest.fixture(autouse=True)
def clean():
    init_db()
    with SessionLocal() as db:
        for model in (Message, Handoff, Booking, Conversation):
            db.query(model).filter_by(garage_id=GARAGE).delete()
        db.commit()
    yield


def seed():
    """A small but realistic month: 4 chats, 2 bookings, 1 handoff, 1 blocked reply."""
    with SessionLocal() as db:
        ids = []
        for i, (lang, outside) in enumerate(
            [("en", False), ("ar", True), ("en", True), ("ur", False)]
        ):
            conv = Conversation(
                garage_id=GARAGE, customer_number="97150000000%d" % i,
                language=lang, started_outside_hours=outside,
                started_at=START + timedelta(days=i + 1),
                last_message_at=START + timedelta(days=i + 1),
            )
            db.add(conv)
            db.flush()
            ids.append(conv.id)

        for conv_id, intent, secs in [
            (ids[0], "price", 3.0), (ids[1], "price", 5.0),
            (ids[2], "booking", 9.0), (ids[3], "info", 1.0),
        ]:
            db.add(Message(
                garage_id=GARAGE, conversation_id=conv_id, direction="out", sender="bot",
                body="reply", intent=intent, reply_seconds=secs,
                created_at=START + timedelta(days=2),
            ))

        for conv_id, statusv in [(ids[0], "confirmed"), (ids[2], "confirmed"), (ids[3], "cancelled")]:
            db.add(Booking(
                garage_id=GARAGE, conversation_id=conv_id, customer_name="Ahmed",
                customer_number="971500000000", car="Camry 2019", service="Oil change",
                slot_start=START + timedelta(days=5), status=statusv,
                created_at=START + timedelta(days=3),
            ))

        db.add(Handoff(garage_id=GARAGE, conversation_id=ids[1], reason="off sheet: gearbox",
                       created_at=START + timedelta(days=3)))
        db.add(Handoff(garage_id=GARAGE, conversation_id=ids[3],
                       reason="blocked: numbers not in the source data",
                       created_at=START + timedelta(days=4)))
        db.commit()
        return ids


# --- the numbers ------------------------------------------------------------

def test_the_headline_numbers():
    seed()
    r = report.build(GARAGE, START, END)
    assert r.conversations == 4
    assert r.conversations_outside_hours == 2
    assert r.price_questions == 2
    assert r.bookings == 2
    assert r.bookings_cancelled == 1
    assert r.handoffs == 2
    assert r.replies_sent == 4


def test_median_reply_time_is_a_median_not_an_average():
    seed()
    # 1, 3, 5, 9 -> median 4, mean would be 4.5
    assert report.build(GARAGE, START, END).median_reply_seconds == 4.0


def test_language_breakdown():
    seed()
    assert report.build(GARAGE, START, END).languages == {"en": 2, "ar": 1, "ur": 1}


def test_blocked_replies_are_counted_separately():
    """Every one of these is a reply the guard stopped. Worth watching."""
    seed()
    assert report.build(GARAGE, START, END).replies_blocked == 1


def test_nothing_outside_the_window_is_counted():
    seed()
    r = report.build(GARAGE, START, START + timedelta(days=1))
    assert r.conversations == 0 and r.bookings == 0


def test_an_empty_period_does_not_divide_by_zero():
    r = report.build(GARAGE, START, END)
    assert r.conversations == 0
    assert r.median_reply_seconds is None
    assert r.outside_hours_share == 0.0
    assert r.booking_rate == 0.0
    assert "no data" in report.render(r)


def test_the_rendered_report_reads_like_something_you_would_send_an_owner():
    seed()
    text = report.render(report.build(GARAGE, START, END))
    assert "Conversations          4" in text
    assert "started after hours  2 (50%)" in text
    assert "English" in text and "Arabic" in text
    assert "2 in 4 conversations turned into a booking (50%)" in text


# --- the command line -------------------------------------------------------

def test_the_cli_prints_the_report(capsys):
    seed()
    assert cli_main(["report", "--garage", GARAGE, "--from", "2026-09-01", "--to", "2026-09-30"]) == 0
    assert "Conversations          4" in capsys.readouterr().out


def test_the_cli_rejects_a_backwards_range():
    assert cli_main(["report", "--garage", GARAGE, "--from", "2026-09-30", "--to", "2026-09-01"]) == 2


def test_the_check_command_flags_an_unfinished_price_sheet(capsys):
    """care/prices.yaml still has TODOs in it, and that must be visible."""
    code = cli_main(["check", "--garage", "care"])
    out = capsys.readouterr().out
    assert "unfilled" in out
    assert code == 1


# --- the admin page ---------------------------------------------------------

def test_admin_without_login_goes_to_the_login_page():
    r = client.get("/admin/", follow_redirects=False)
    assert r.status_code == 307 and "/admin/login" in r.headers["location"]
    r2 = client.get("/admin/bookings", follow_redirects=False)
    assert r2.status_code == 307


def test_login_sets_a_session_then_grants_access():
    fresh = TestClient(app)
    bad = fresh.post("/admin/login", data={"username": "admin", "password": "nope"},
                     follow_redirects=False)
    assert bad.status_code == 200 and "Wrong username or password" in bad.text
    ok = fresh.post("/admin/login", data={"username": "admin", "password": "test-password"},
                    follow_redirects=False)
    assert ok.status_code == 303
    # the session cookie now grants access without any auth header
    assert fresh.get("/admin/").status_code == 200
    # logout clears it
    fresh.get("/admin/logout")
    assert fresh.get("/admin/", follow_redirects=False).status_code == 307


def test_admin_lists_conversations():
    seed()
    r = client.get("/admin/", headers=AUTH)
    assert r.status_code == 200
    assert "971500000000" in r.text


def test_admin_shows_a_transcript_with_the_handoff_marked():
    ids = seed()
    r = client.get("/admin/conversation/%d" % ids[1], headers=AUTH)
    assert r.status_code == 200
    assert "handed over" in r.text.lower()
    assert "off sheet: gearbox" in r.text, "the reason must be readable, not just a flag"


def test_admin_escapes_what_a_customer_typed():
    """A customer message is untrusted text. It renders, it does not execute."""
    ids = seed()
    with SessionLocal() as db:
        db.add(Message(garage_id=GARAGE, conversation_id=ids[0], direction="in",
                       sender="customer", body="<script>alert(1)</script>"))
        db.commit()
    r = client.get("/admin/conversation/%d" % ids[0], headers=AUTH)
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


def test_admin_report_page_renders():
    seed()
    r = client.get("/admin/report?garage=%s&days=60" % GARAGE, headers=AUTH)
    assert r.status_code == 200 and "Conversations" in r.text


def test_a_missing_conversation_is_a_404():
    assert client.get("/admin/conversation/999999", headers=AUTH).status_code == 404


def test_releasing_a_handed_over_chat_gives_it_back_to_the_bot():
    ids = seed()  # ids[1] has an open handoff ("off sheet: gearbox")
    with SessionLocal() as db:
        assert db.query(Handoff).filter_by(conversation_id=ids[1], released_at=None).count() >= 1
    r = client.post("/admin/conversation/%d/release" % ids[1], headers=AUTH, follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.query(Handoff).filter_by(conversation_id=ids[1], released_at=None).count() == 0
        assert db.get(Conversation, ids[1]).paused_until is None


def test_the_release_button_shows_on_a_handed_over_transcript():
    ids = seed()
    r = client.get("/admin/conversation/%d" % ids[1], headers=AUTH)
    assert "/release" in r.text and "back to the bot" in r.text.lower()


def test_the_root_is_the_public_landing_page():
    """The bare domain shows what the tool is — safe to send to anyone."""
    r = client.get("/")
    assert r.status_code == 200
    assert "WhatsApp assistant" in r.text
    assert "971" not in r.text  # no customer data on the public page
