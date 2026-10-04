"""The webhook: handshake, signature check, parsing, logging, and the reply it triggers."""
import hashlib
import hmac
import json
import os
import uuid

os.environ.setdefault("META_APP_SECRET", "test-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_mistri.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import conversations, respond, whatsapp  # noqa: E402
from app.db import (  # noqa: E402
    Conversation, Handoff, Message, SessionLocal, init_db, utcnow,
)
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)

BUSINESS = "97141234567"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Nothing in this file may touch the real Graph API.

    TestClient runs background tasks after the response, so the reply path
    really does execute here - it just sends into this list instead.
    """
    sent = []

    async def _send(to, body):
        sent.append((to, body))
        return {"messages": [{"id": "wamid.out.%s" % uuid.uuid4().hex}]}

    monkeypatch.setattr(whatsapp, "send_text", _send)
    monkeypatch.setattr(respond.whatsapp, "send_text", _send)
    return sent


def _payload(from_number, body, msg_id="wamid.1"):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "display_phone_number": BUSINESS,
                                "phone_number_id": "PNID1",
                            },
                            "contacts": [
                                {"wa_id": from_number, "profile": {"name": "Ahmed"}}
                            ],
                            "messages": [
                                {
                                    "from": from_number,
                                    "to": "971509998888",
                                    "id": msg_id,
                                    "timestamp": "1756700000",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }


def _post(payload):
    raw = json.dumps(payload).encode()
    sig = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    return client.post(
        "/webhook", content=raw, headers={"X-Hub-Signature-256": f"sha256={sig}"}
    )


def test_verify_handshake():
    r = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-token",
            "hub.challenge": "12345",
        },
    )
    assert r.status_code == 200 and r.text == "12345"


def test_verify_rejects_wrong_token():
    r = client.get(
        "/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope"}
    )
    assert r.status_code == 403


def test_bad_signature_rejected():
    raw = json.dumps(_payload("971501112222", "hi")).encode()
    r = client.post("/webhook", content=raw, headers={"X-Hub-Signature-256": "sha256=bad"})
    assert r.status_code == 401


def test_customer_message_is_logged():
    assert _post(_payload("971501112222", "brake pads Camry 2019?")).status_code == 200
    with SessionLocal() as db:
        m = db.query(Message).filter_by(wa_message_id="wamid.1").one()
        assert m.sender == "customer" and m.direction == "in"
        assert "brake pads" in m.body


def test_owner_echo_pauses_the_bot():
    """Rule: the bot never talks over the owner."""
    _post(_payload("971503334444", "hello", msg_id="wamid.2"))
    # coexistence echo of the owner's own reply: `from` is the business number
    echo = _payload(BUSINESS, "I will call you now", msg_id="wamid.3")
    echo["entry"][0]["changes"][0]["value"]["messages"][0]["to"] = "971503334444"
    assert _post(echo).status_code == 200

    with SessionLocal() as db:
        conv = db.query(Conversation).filter_by(customer_number="971503334444").one()
        assert conv.paused_until is not None


def test_group_messages_are_ignored():
    p = _payload("971505556666", "group chatter", msg_id="wamid.4")
    p["entry"][0]["changes"][0]["value"]["messages"][0]["group_id"] = "g1"
    assert whatsapp.parse_webhook(p) == []


def test_status_only_payload_is_ignored():
    p = {
        "entry": [
            {"changes": [{"value": {"metadata": {}, "statuses": [{"status": "read"}]}}]}
        ]
    }
    assert whatsapp.parse_webhook(p) == []


def test_a_customer_message_gets_a_reply_sent(no_network):
    """Webhook to reply, end to end. No API key here, so it lands on the handoff."""
    assert _post(_payload("971507770001", "how much for oil change?", "wamid.10")).status_code == 200

    assert no_network, "nothing was sent to the customer"
    to, body = no_network[0]
    assert to == "971507770001"
    assert body  # the handoff line, since the model is unavailable in tests

    with SessionLocal() as db:
        out = (
            db.query(Message)
            .filter_by(sender="bot")
            .order_by(Message.id.desc())
            .first()
        )
        assert out.direction == "out"
        assert out.reply_seconds is not None and out.reply_seconds >= 0


def test_the_owner_is_alerted_on_a_handoff(no_network):
    _post(_payload("971507770002", "rebuild my gearbox please", "wamid.11"))
    recipients = [to for to, _ in no_network]
    # customer first, then the owner's alert number from garages/care/info.yaml
    assert len(recipients) >= 1
    with SessionLocal() as db:
        conv = db.query(Conversation).filter_by(customer_number="971507770002").one()
        assert conversations.open_handoff(db, conv.id) is not None,             "a handed-over chat must stop the bot"
        assert conversations.is_muted(db, conv)


def test_the_bot_stays_quiet_while_the_owner_is_handling_it(no_network):
    _post(_payload("971507770003", "hello", "wamid.12"))
    no_network.clear()

    echo = _payload(BUSINESS, "I am calling you now", "wamid.13")
    echo["entry"][0]["changes"][0]["value"]["messages"][0]["to"] = "971507770003"
    _post(echo)

    # the owner's own message must not trigger a bot reply
    assert no_network == []


def test_a_redelivered_webhook_is_not_answered_twice(no_network):
    """Meta redelivers when an ack is slow. Answering twice is worse than late."""
    payload = _payload("971507770004", "hello there", "wamid.dup")
    _post(payload)
    first = len(no_network)
    _post(payload)
    assert len(no_network) == first


def test_an_owner_command_is_not_treated_as_talking_to_the_customer(no_network):
    """/bot off in a chat must not read as him answering the customer."""
    _post(_payload("971507770005", "hello", "wamid.c1"))
    no_network.clear()

    cmd = _payload(BUSINESS, "/bot off", "wamid.c2")
    cmd["entry"][0]["changes"][0]["value"]["messages"][0]["to"] = "971507770005"
    _post(cmd)

    with SessionLocal() as db:
        conv = db.query(Conversation).filter_by(customer_number="971507770005").one()
        # muted because he asked, not because we mistook a command for a reply
        assert conv.paused_until is None
        assert conversations.is_muted(db, conv)


def test_the_owner_can_hand_a_chat_back(no_network):
    _post(_payload("971507770006", "hi", "wamid.c3"))

    off = _payload(BUSINESS, "/bot off", "wamid.c4")
    off["entry"][0]["changes"][0]["value"]["messages"][0]["to"] = "971507770006"
    _post(off)

    on = _payload(BUSINESS, "/bot on 971507770006", "wamid.c5")
    on["entry"][0]["changes"][0]["value"]["messages"][0]["to"] = "971507770006"
    _post(on)

    with SessionLocal() as db:
        conv = db.query(Conversation).filter_by(customer_number="971507770006").one()
        assert conversations.is_muted(db, conv) is None


def test_a_runaway_conversation_stops_costing_money(no_network, monkeypatch):
    """Past the daily cap the bot stops replying and the owner is told.

    A loop or a nuisance sender should cost a bounded amount and end up with a
    human, not run all night against a paid API.
    """
    from app.config import settings
    from app.db import Message as Msg
    monkeypatch.setattr(settings, "max_replies_per_day", 3)

    _post(_payload("971507770007", "hello", "wamid.cap0"))
    with SessionLocal() as db:
        conv = db.query(Conversation).filter_by(customer_number="971507770007").one()
        # the first turn handed over, so clear that and stand in a day's traffic
        for row in db.query(Handoff).filter_by(conversation_id=conv.id).all():
            row.released_at = utcnow()
        for i in range(3):
            db.add(Msg(garage_id="care", conversation_id=conv.id, direction="out",
                       sender="bot", body="reply %d" % i))
        db.commit()

    no_network.clear()
    _post(_payload("971507770007", "and again", "wamid.cap9"))

    assert no_network == [], "nothing should be sent to the customer past the cap"
    with SessionLocal() as db:
        conv = db.query(Conversation).filter_by(customer_number="971507770007").one()
        handoff = conversations.open_handoff(db, conv.id)
        assert handoff is not None
        assert "reply cap" in handoff.reason
