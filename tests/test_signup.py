"""Self-service signup + owner login.

A garage owner creates an account on the website, lands in onboarding, and can
log back in later with their number + password to reach only their own garage.
"""
import shutil

import pytest
from fastapi.testclient import TestClient

from app import garages, onboard, owners
from app.db import Lead, Owner, SessionLocal, init_db
from app.main import app

client = TestClient(app)
_CREATED: list[str] = []
PW = "secret123"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    # The signup background task WhatsApps a confirmation; don't hit the network in tests.
    async def _noop(*a, **k):
        return {"messages": [{"id": "test"}]}
    monkeypatch.setattr("app.whatsapp.send_template", _noop)

    init_db()
    with SessionLocal() as db:
        db.query(Lead).delete()
        db.query(Owner).delete()
        db.commit()
    yield
    for gid in _CREATED:
        shutil.rmtree(onboard.GARAGES_DIR / gid, ignore_errors=True)
        garages._cache.pop(gid, None)
    _CREATED.clear()


def _signup(name, number, password=PW, area=""):
    r = client.post("/start", data={"name": name, "number": number,
                                    "password": password, "area": area},
                    follow_redirects=False)
    if r.status_code == 303:
        gid = r.headers["location"].split("/onboard/")[1].split("?")[0]
        _CREATED.append(gid)
    return r


def _owner_cookie(gid):
    return {"Cookie": "%s=%s" % (owners.OWNER_COOKIE, owners._sign(gid))}


# --- signup -----------------------------------------------------------------

def test_the_start_page_loads():
    r = client.get("/start")
    assert r.status_code == 200 and "Set up your garage" in r.text


def test_signup_creates_a_pending_garage_an_account_and_redirects():
    r = _signup("Test Signup Garage", "0501112233", area="Al Quoz")
    assert r.status_code == 303
    gid = r.headers["location"].split("/onboard/")[1].split("?")[0]

    g = garages.load(gid)
    assert g["info"]["pending"] is True
    assert g["info"]["owner_alert_number"] == "971501112233"
    assert gid not in garages.routable_ids()
    assert garages.routable_ids() == ["care"]
    # an owner account now exists for that number
    assert owners.authenticate("971501112233", PW) == gid


def test_a_short_password_is_rejected():
    r = client.post("/start", data={"name": "X Garage", "number": "0501110000",
                                    "password": "123"}, follow_redirects=False)
    assert r.status_code == 200 and "at least 6" in r.text


def test_a_duplicate_number_is_sent_to_login():
    _signup("First Garage", "0505550000")
    r = client.post("/start", data={"name": "Second Garage", "number": "0505550000",
                                    "password": PW}, follow_redirects=False)
    assert r.status_code == 200 and "already set up" in r.text


def test_signup_notifies_the_operator():
    _signup("Notify Garage", "0509998877")
    with SessionLocal() as db:
        assert any("NEW GARAGE" in l.name for l in db.query(Lead).all())


# --- owner login ------------------------------------------------------------

def test_owner_can_log_in_with_number_and_password():
    r = _signup("Login Garage", "0501010101")
    gid = r.headers["location"].split("/onboard/")[1].split("?")[0]

    ok = client.post("/login", data={"number": "0501010101", "password": PW},
                     follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/owner"

    bad = client.post("/login", data={"number": "0501010101", "password": "wrong"},
                      follow_redirects=False)
    assert bad.status_code == 200 and "Wrong number or password" in bad.text


def test_owner_login_reaches_only_their_own_garage():
    r = _signup("Cookie Garage", "0502020202")
    gid = r.headers["location"].split("/onboard/")[1].split("?")[0]

    # /owner with the owner cookie bounces to their home page
    home = client.get("/owner", headers=_owner_cookie(gid), follow_redirects=False)
    assert home.status_code == 307 and gid in home.headers["location"]

    # their onboarding page opens on the cookie alone — no token needed
    page = client.get("/onboard/%s/home" % gid, headers=_owner_cookie(gid))
    assert page.status_code == 200 and "Cookie Garage" in page.text


def test_a_pending_signup_shows_on_the_admin_setup_page():
    from app.admin import SESSION_COOKIE, _session_value
    r = _signup("Visible Garage", "0506060606")
    gid = r.headers["location"].split("/onboard/")[1].split("?")[0]
    admin_cookie = {"Cookie": "%s=%s" % (SESSION_COOKIE, _session_value())}
    page = client.get("/admin/setup", headers=admin_cookie)
    assert page.status_code == 200
    assert "Visible Garage" in page.text        # the signup is listed
    assert "Setting up" in page.text            # with a pending status


def test_admin_can_delete_a_garage():
    from app.admin import SESSION_COOKIE, _session_value
    r = _signup("Deletable Garage", "0507070707")
    gid = r.headers["location"].split("/onboard/")[1].split("?")[0]
    admin_cookie = {"Cookie": "%s=%s" % (SESSION_COOKIE, _session_value())}

    d = client.post("/admin/garage/%s/delete" % gid, headers=admin_cookie,
                    follow_redirects=False)
    assert d.status_code == 303
    assert not (onboard.GARAGES_DIR / gid).exists()          # files gone
    with SessionLocal() as db:                               # owner login gone
        assert db.query(Owner).filter_by(garage_id=gid).first() is None


def test_deleting_a_garage_needs_admin_login():
    r = _signup("Guarded Garage", "0508080808")
    gid = r.headers["location"].split("/onboard/")[1].split("?")[0]
    d = client.post("/admin/garage/%s/delete" % gid, follow_redirects=False)
    assert d.status_code == 307 and "/admin/login" in d.headers["location"]
    assert (onboard.GARAGES_DIR / gid).exists()             # untouched


def test_owner_without_login_goes_to_login():
    r = client.get("/owner", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/login"


def test_a_stranger_cannot_open_a_garage_without_token_or_cookie():
    r = _signup("Locked Garage", "0503030303")
    gid = r.headers["location"].split("/onboard/")[1].split("?")[0]
    # no token, no cookie
    assert client.get("/onboard/%s/home" % gid).status_code == 403


def test_saving_lands_on_the_owner_home_page():
    r = _signup("Home Garage", "0504040404")
    gid = r.headers["location"].split("/onboard/")[1].split("?")[0]
    t = onboard.token_for(gid)

    save = client.post("/onboard/%s?t=%s" % (gid, t),
                       data={"svc_name": "Oil change", "svc_id": "oil_change",
                             "price_sedan": "180", "price_suv": "", "price_luxury": "",
                             "svc_note": ""}, follow_redirects=False)
    assert save.status_code == 303 and "/home" in save.headers["location"]

    page = client.get("/onboard/%s/home?t=%s" % (gid, t))
    assert page.status_code == 200
    assert "Home Garage" in page.text and "Edit my prices" in page.text
