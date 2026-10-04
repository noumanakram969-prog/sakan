"""The public demo form and the admin message inbox it feeds."""
import pytest
from fastapi.testclient import TestClient

from app.admin import SESSION_COOKIE, _session_value
from app.db import Lead, SessionLocal, init_db
from app.main import app

client = TestClient(app)
# Admin auth is cookie-only now; a Cookie header authenticates the request.
AUTH = {"Cookie": "%s=%s" % (SESSION_COOKIE, _session_value())}


@pytest.fixture(autouse=True)
def clean():
    init_db()
    with SessionLocal() as db:
        db.query(Lead).delete()
        db.commit()
    yield


def test_the_form_stores_a_lead():
    r = client.post("/contact", data={"name": "Bilal", "number": "0501234567",
                                      "message": "want a demo"})
    assert r.status_code == 200 and "Message received" in r.text
    with SessionLocal() as db:
        rows = db.query(Lead).all()
    assert len(rows) == 1 and rows[0].number == "0501234567" and rows[0].handled is False


def test_an_empty_submit_stores_nothing():
    client.post("/contact", data={"name": "", "number": "", "message": ""})
    with SessionLocal() as db:
        assert db.query(Lead).count() == 0


def test_the_message_shows_in_the_admin_inbox():
    client.post("/contact", data={"number": "0509999999", "message": "hi there"})
    r = client.get("/admin/messages", headers=AUTH)
    assert r.status_code == 200
    assert "0509999999" in r.text and "hi there" in r.text


def test_marking_a_message_done():
    client.post("/contact", data={"number": "0508887777", "message": "demo please"})
    with SessionLocal() as db:
        lead_id = db.query(Lead).one().id
    r = client.post("/admin/messages/%d/done" % lead_id, headers=AUTH, follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.get(Lead, lead_id).handled is True


def test_the_inbox_needs_a_login():
    r = client.get("/admin/messages", follow_redirects=False)
    assert r.status_code == 307 and "/admin/login" in r.headers["location"]


def test_the_setup_page_shows_the_owner_edit_link():
    r = client.get("/admin/setup", headers=AUTH)
    assert r.status_code == 200
    # the owner's private, tokenised edit link is on the page
    assert "/onboard/" in r.text and "t=" in r.text


def test_the_setup_page_needs_a_login():
    r = client.get("/admin/setup", follow_redirects=False)
    assert r.status_code == 307 and "/admin/login" in r.headers["location"]
