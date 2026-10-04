"""Owner commands, and the mute rules they drive.

The owner will type these one-handed, in a hurry, in a chat. Being forgiving
about format matters more here than being clever.
"""
from datetime import datetime, timedelta

import pytest

from app import commands, conversations
from app.db import Conversation, Handoff, SessionLocal, init_db, utcnow

GARAGE = "cmdtest"
CUSTOMER = "971501234567"


@pytest.fixture(autouse=True)
def clean():
    init_db()
    with SessionLocal() as db:
        for conv in db.query(Conversation).filter_by(garage_id=GARAGE).all():
            db.query(Handoff).filter_by(conversation_id=conv.id).delete()
        db.query(Conversation).filter_by(garage_id=GARAGE).delete()
        db.commit()
    conversations.set_bot_enabled(GARAGE, True)
    yield


def make_conversation(last_message_at=None, paused_until=None) -> int:
    with SessionLocal() as db:
        conv = Conversation(
            garage_id=GARAGE,
            customer_number=CUSTOMER,
            last_message_at=last_message_at or utcnow(),
            paused_until=paused_until,
        )
        db.add(conv)
        db.commit()
        return conv.id


# --- parsing ----------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "/bot on 0501234567",
    "bot on 0501234567",
    "/BOT ON 0501234567",
    "  /bot   on   050 123 4567  ",
    "/bot on +971 50 123 4567",
    "/bot on (050) 123-4567",
])
def test_release_is_recognised_however_he_types_it(text):
    cmd = commands.parse(text)
    assert cmd is not None
    assert cmd.action == "on"
    assert cmd.number == "971501234567"


def test_off_with_a_number():
    cmd = commands.parse("/bot off 0501234567")
    assert cmd.action == "off" and cmd.number == "971501234567"


def test_no_number_means_this_chat_or_everyone():
    assert commands.parse("/bot off") == commands.Command("off", None)
    assert commands.parse("/bot on") == commands.Command("on", None)


def test_status_and_help():
    assert commands.parse("/status").action == "status"
    assert commands.parse("help").action == "help"


@pytest.mark.parametrize("text", [
    "",
    "hi, I'll call you in 5 minutes",
    "bot",
    "/bot maybe",
    "the bot on my car is fine",
    "/status 0501234567",
    "can you turn the bot on for him?",
])
def test_ordinary_messages_are_not_commands(text):
    """A false positive here silences the bot for a customer. Be strict."""
    assert commands.parse(text) is None


@pytest.mark.parametrize("raw,expected", [
    ("0501234567", "971501234567"),
    ("971501234567", "971501234567"),
    ("+971501234567", "971501234567"),
    ("00971501234567", "971501234567"),
    ("501234567", "971501234567"),
    ("abc", None),
    ("12", None),
    ("", None),
    (None, None),
])
def test_number_normalisation(raw, expected):
    assert commands.normalise(raw) == expected


# --- what the commands actually do ------------------------------------------

def test_a_handed_over_chat_is_muted():
    conv_id = make_conversation()
    with SessionLocal() as db:
        db.add(Handoff(garage_id=GARAGE, conversation_id=conv_id, reason="off sheet"))
        db.commit()
        conv = db.get(Conversation, conv_id)
        assert conversations.is_muted(db, conv) == "handed over, waiting for release"


def test_release_gives_the_chat_back():
    conv_id = make_conversation()
    with SessionLocal() as db:
        db.add(Handoff(garage_id=GARAGE, conversation_id=conv_id, reason="off sheet"))
        db.commit()

    conversations.release(GARAGE, CUSTOMER)

    with SessionLocal() as db:
        conv = db.get(Conversation, conv_id)
        assert conversations.is_muted(db, conv) is None


def test_release_also_clears_an_owner_pause():
    conv_id = make_conversation(paused_until=utcnow() + timedelta(hours=2))
    conversations.release(GARAGE, CUSTOMER)
    with SessionLocal() as db:
        assert db.get(Conversation, conv_id).paused_until is None


def test_the_owner_can_take_a_chat_off_the_bot():
    conv_id = make_conversation()
    conversations.hand_to_owner(GARAGE, CUSTOMER)
    with SessionLocal() as db:
        conv = db.get(Conversation, conv_id)
        assert conversations.is_muted(db, conv)


def test_the_kill_switch_stops_every_chat():
    conv_id = make_conversation()
    conversations.set_bot_enabled(GARAGE, False)
    with SessionLocal() as db:
        conv = db.get(Conversation, conv_id)
        assert conversations.is_muted(db, conv) == "bot off for this garage"

    conversations.set_bot_enabled(GARAGE, True)
    with SessionLocal() as db:
        assert conversations.is_muted(db, db.get(Conversation, conv_id)) is None


# --- auto-release -----------------------------------------------------------

def test_a_quiet_handoff_releases_itself():
    conv_id = make_conversation(last_message_at=utcnow() - timedelta(hours=30))
    with SessionLocal() as db:
        db.add(Handoff(garage_id=GARAGE, conversation_id=conv_id, reason="off sheet"))
        db.commit()

    assert conversations.auto_release_quiet_handoffs() >= 1

    with SessionLocal() as db:
        assert conversations.is_muted(db, db.get(Conversation, conv_id)) is None


def test_an_active_handoff_is_left_alone():
    """Still talking to the owner. The bot stays out however long that takes."""
    conv_id = make_conversation(last_message_at=utcnow() - timedelta(hours=2))
    with SessionLocal() as db:
        db.add(Handoff(garage_id=GARAGE, conversation_id=conv_id, reason="off sheet"))
        db.commit()

    conversations.auto_release_quiet_handoffs()

    with SessionLocal() as db:
        assert conversations.is_muted(db, db.get(Conversation, conv_id))


def test_releasing_twice_is_harmless():
    conv_id = make_conversation(last_message_at=utcnow() - timedelta(hours=30))
    with SessionLocal() as db:
        db.add(Handoff(garage_id=GARAGE, conversation_id=conv_id, reason="x"))
        db.commit()
    conversations.auto_release_quiet_handoffs()
    assert conversations.auto_release_quiet_handoffs() == 0


# --- what the owner actually reads ------------------------------------------

@pytest.mark.parametrize("internal,expected", [
    ("off sheet: service 'gearbox_rebuild' is not on the sheet",
     "Asked the price of something not on your price list"),
    ("booking off sheet: service 'respray' is not on the sheet",
     "Wants to book something that is not on your price list"),
    ("low confidence on service or car",
     "I could not tell which service or which car they meant"),
    ("blocked: numbers not in the source data",
     "My reply did not look right, so I stopped it and called you instead"),
    ("cannot read a voice note", "Sent a voice note"),
    ("cannot read a photo", "Sent a photo"),
    ("no slots available in the next two weeks",
     "Wanted to book, but nothing is free in the next two weeks"),
    ("reply cap reached (40 today)", "Too many messages in one day from this number"),
    ("classifier unavailable", "Something went wrong on my side"),
    ("owner asked", "You took this chat yourself"),
])
def test_the_owner_reads_a_sentence_not_a_reason_code(internal, expected):
    """He gets these on his phone. "blocked: numbers not in the source data"
    reads as something being broken."""
    from app import wording
    assert wording.plain_reason(internal) == expected


def test_an_unknown_reason_still_says_something_sensible():
    from app import wording
    assert wording.plain_reason("something nobody wrote a phrase for") == wording.FALLBACK
    assert wording.plain_reason(None) == wording.FALLBACK
    assert wording.plain_reason("") == wording.FALLBACK


def test_no_internal_reason_leaks_through():
    """Every reason the engine can produce must map to a plain sentence."""
    from app import engine, wording
    produced = [
        "off sheet: no price on the sheet for oil_change / suv",
        "booking off sheet: x", "low confidence on service or car",
        "blocked: mentions money with no price looked up",
        "cannot read a photo", "cannot read a voice note",
        "info topic not in the garage files", "no slots available in the next two weeks",
        "reply cap reached (40 today)", "classifier unavailable", "composer unavailable",
        "engine error - see the log", "no conversation context for booking",
        "intent not handled in v1: other", "owner asked",
    ]
    for reason in produced:
        assert wording.plain_reason(reason) != wording.FALLBACK, reason
    assert engine.HANDOFF["en"]
