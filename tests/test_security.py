"""The findings from the pre-go-live review, each pinned by a test.

Every one of these was a real defect in code that passed 254 other tests. They
are here so that a later refactor cannot quietly reintroduce them.
"""
import base64

import pytest
from fastapi.testclient import TestClient

from app import garages, whatsapp
from app.config import settings
from app.main import app

client = TestClient(app)

BUSINESS_DIGITS = "97141234567"


def payload(from_number, display_phone_number, to="971501112222"):
    return {
        "entry": [{"changes": [{"value": {
            "metadata": {"display_phone_number": display_phone_number,
                         "phone_number_id": "PNID1"},
            "messages": [{"from": from_number, "to": to, "id": "wamid.x",
                          "timestamp": "1756700000", "type": "text",
                          "text": {"body": "I will call you now"}}],
        }}]}]
    }


# --- 1. the owner's own replies must be recognised as his -------------------

@pytest.mark.parametrize("display", [
    "97141234567",          # bare, as the docs show it
    "+97141234567",         # with a plus
    "+971 4 123 4567",      # formatted for humans, which is what Meta returns
    "+971-4-123-4567",
    " 971 4 123 4567 ",
])
def test_the_owner_echo_is_recognised_however_meta_formats_the_number(display):
    """If this fails, the bot talks over the owner in every chat.

    display_phone_number comes back formatted for display while `from` is bare
    digits, so comparing the raw strings classifies every one of his replies as
    a customer message - and the whole handoff design rests on that comparison.
    """
    messages = whatsapp.parse_webhook(payload(BUSINESS_DIGITS, display))
    assert len(messages) == 1
    assert messages[0].sender == "owner"
    # the conversation is the customer he was writing to, not himself
    assert messages[0].from_number == "971501112222"


def test_a_customer_is_still_a_customer():
    messages = whatsapp.parse_webhook(payload("971509998888", "+971 4 123 4567"))
    assert messages[0].sender == "customer"
    assert messages[0].from_number == "971509998888"


def test_a_missing_business_number_does_not_make_everyone_the_owner():
    """Failing the other way would silence the bot for every customer."""
    messages = whatsapp.parse_webhook(payload("971509998888", ""))
    assert messages[0].sender == "customer"


# --- 2. a BSP webhook is not open to the world ------------------------------

def test_meta_webhooks_still_need_a_valid_signature(monkeypatch):
    monkeypatch.setattr(settings, "wa_provider", "meta")
    assert not whatsapp.verify_signature(b"{}", "sha256=deadbeef")
    assert not whatsapp.verify_signature(b"{}", None)


def test_a_bsp_webhook_without_the_shared_secret_is_refused(monkeypatch):
    """360dialog does not sign anything.

    An open webhook here is not a small problem: anyone who finds the URL could
    post invented customer messages and make the garage's own number send
    WhatsApp messages to whatever number they name.
    """
    monkeypatch.setattr(settings, "wa_provider", "d360")
    monkeypatch.setattr(settings, "webhook_token", "s3cret")

    assert whatsapp.verify_signature(b"{}", None, "s3cret")
    assert not whatsapp.verify_signature(b"{}", None, "wrong")
    assert not whatsapp.verify_signature(b"{}", None, None)


def test_a_bsp_with_no_secret_configured_fails_closed(monkeypatch):
    """Unset means refuse everything, not allow everything."""
    monkeypatch.setattr(settings, "wa_provider", "d360")
    monkeypatch.setattr(settings, "webhook_token", "")
    assert not whatsapp.verify_signature(b"{}", None, None)
    assert not whatsapp.verify_signature(b"{}", None, "anything")


def test_the_endpoint_rejects_an_unauthenticated_post():
    assert client.post("/webhook", json={"entry": []}).status_code == 401


# --- 3. the admin page will not serve on the shipped password ---------------

def test_admin_refuses_to_serve_on_the_default_password(monkeypatch):
    """It lists customers' numbers and everything they ever wrote.

    On the default it is protected by a password that is in the repository, so
    it says so rather than pretending to be secured.
    """
    monkeypatch.setattr(settings, "admin_password", "change-me")
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:change-me").decode()}
    r = client.get("/admin/", headers=auth)
    assert r.status_code == 503
    assert "ADMIN_PASSWORD" in r.text


def test_http_basic_no_longer_authenticates_the_admin(monkeypatch):
    """Cookie-only: even a *correct* Basic header must not get in, or a browser's
    cached Basic password could defeat logout."""
    monkeypatch.setattr(settings, "admin_password", "a-real-password")
    right = {"Authorization": "Basic " + base64.b64encode(b"admin:a-real-password").decode()}
    r = client.get("/admin/", headers=right, follow_redirects=False)
    assert r.status_code == 307 and "/admin/login" in r.headers["location"]


def test_a_wrong_session_cookie_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "a-real-password")
    r = client.get("/admin/", headers={"Cookie": "mistri_admin=not-the-real-value"},
                   follow_redirects=False)
    assert r.status_code == 307 and "/admin/login" in r.headers["location"]


# --- 4. a garage id names a directory ---------------------------------------

@pytest.mark.parametrize("bad", [
    "../etc", "..", "care/../demo", "/etc/passwd", "care\\..\\demo", "", "Care", "care ",
])
def test_a_garage_id_cannot_walk_the_filesystem(bad):
    with pytest.raises(garages.GarageNotFound):
        garages.load(bad)


def test_real_garages_still_load():
    assert garages.load("care")["id"] == "care"
    assert garages.load("demo")["id"] == "demo"


# --- 5. a model that answers in the wrong shape ------------------------------

@pytest.mark.parametrize("read", [
    {"intent": "price", "confidence": "high", "language": "en"},
    {"intent": "price", "confidence": "0.9", "language": "en"},
    {"intent": "price", "confidence": None, "language": None},
    {"intent": ["price"], "confidence": 0.9, "language": "en"},
    {"intent": None, "confidence": {}, "language": 7},
    {},
])
def test_a_badly_shaped_classifier_answer_never_ends_the_turn(monkeypatch, read):
    """A model asked for JSON returns JSON-shaped, not JSON-typed.

    "confidence": "high" is a plausible thing for it to say, and it used to end
    the turn with a ValueError - which reaches the customer as silence, the one
    outcome worse than handing over.
    """
    from app import engine
    monkeypatch.setattr(engine, "classify", lambda *a, **k: read)
    monkeypatch.setattr(engine, "compose", lambda *a, **k: "ok")

    reply = engine.build_reply({"id": "x", "info": {}, "prices": {"services": []}}, "hi")
    assert isinstance(reply.text, str) and reply.text


def test_a_classifier_that_returns_a_list_is_survivable(monkeypatch):
    from app import engine
    monkeypatch.setattr(engine, "classify", lambda *a, **k: ["nonsense"])
    monkeypatch.setattr(engine, "compose", lambda *a, **k: "ok")
    assert engine.build_reply({"id": "x", "info": {}, "prices": {}}, "hi").is_handoff


def test_a_string_confidence_is_treated_as_no_confidence(monkeypatch):
    from app import engine
    assert engine._as_confidence("high") == 0.0
    assert engine._as_confidence("0.9") == 0.9
    assert engine._as_confidence(5) == 1.0
    assert engine._as_confidence(-1) == 0.0


# --- 6. a crash must not reach the customer as silence -----------------------

@pytest.mark.asyncio
async def test_an_engine_crash_becomes_a_handover(monkeypatch):
    """Whatever went wrong, no answer at all is worse than getting a person."""
    from app import engine, respond
    from app.db import Conversation, Message, SessionLocal

    sent = []

    async def _send(to, body):
        sent.append((to, body))
        return {"messages": [{"id": "wamid.crash"}]}

    def _boom(*a, **k):
        raise RuntimeError("something nobody predicted")

    monkeypatch.setattr(engine, "build_reply", _boom)
    monkeypatch.setattr(respond.whatsapp, "send_text", _send)

    with SessionLocal() as db:
        conv = Conversation(garage_id="care", customer_number="971509990099")
        db.add(conv)
        db.flush()
        row = Message(garage_id="care", conversation_id=conv.id, direction="in",
                      sender="customer", body="hello")
        db.add(row)
        db.commit()
        ids = (conv.id, row.id)

    await respond.handle(ids[0], "care", ids[1])

    assert sent, "the customer must still get something"
    assert sent[0][0] == "971509990099"


# --- 7. one blip must not lose a reply ---------------------------------------

@pytest.mark.asyncio
async def test_a_transient_send_failure_is_retried(monkeypatch):
    """A customer lost to a single 503 is a customer lost to nothing."""
    import httpx
    monkeypatch.setattr(whatsapp, "SEND_ATTEMPTS", 3)
    monkeypatch.setattr(whatsapp, "RETRY_AFTER_SECONDS", 0)
    monkeypatch.setattr(settings, "wa_provider", "meta")

    calls = []

    class FakeResponse:
        def __init__(self, code):
            self.status_code = code
            self.text = "busy"

        def json(self):
            return {"messages": [{"id": "wamid.ok"}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            calls.append(url)
            return FakeResponse(503 if len(calls) < 3 else 200)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    result = await whatsapp.send_text("971500000000", "hello")
    assert len(calls) == 3
    assert result["messages"][0]["id"] == "wamid.ok"


@pytest.mark.asyncio
async def test_our_own_mistakes_are_not_retried(monkeypatch):
    """A 400 will fail again identically. Retrying it just delays the handover."""
    import httpx
    monkeypatch.setattr(whatsapp, "RETRY_AFTER_SECONDS", 0)
    monkeypatch.setattr(settings, "wa_provider", "meta")
    calls = []

    class FakeResponse:
        status_code = 400
        text = "bad recipient"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            calls.append(url)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    with pytest.raises(whatsapp.WhatsAppError):
        await whatsapp.send_text("971500000000", "hello")
    assert len(calls) == 1


# --- 8. messages that are not somebody asking something ----------------------

@pytest.mark.parametrize("kind", ["system", "reaction", "unsupported", "order"])
def test_non_questions_are_ignored_entirely(kind):
    """A thumbs up on an old message must not alert the owner about nothing."""
    p = payload("971509998888", "+971 4 123 4567")
    p["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = kind
    assert whatsapp.parse_webhook(p) == []


# --- the public privacy policy ----------------------------------------------

def test_the_privacy_policy_is_public():
    """Meta will not clear an app without a reachable privacy policy URL."""
    r = client.get("/privacy")
    assert r.status_code == 200
    assert "Privacy Policy" in r.text


def test_it_says_what_is_actually_stored():
    """If the page and the code disagree, the page is the lie."""
    text = client.get("/privacy").text
    for promise in ["phone number", "messages you send", "Anthropic", "90 days", "STOP"]:
        assert promise in text, promise


def test_the_operator_details_are_configurable(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "operator_name", "Test Trading LLC")
    monkeypatch.setattr(settings, "operator_email", "hello@example.ae")
    text = client.get("/privacy").text
    assert "Test Trading LLC" in text
    assert "hello@example.ae" in text
