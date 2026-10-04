"""Whether the bot may speak, and who decides.

Three separate things can keep it quiet, and they are deliberately separate:

* the owner typed in that chat        -> short pause, hours
* the bot handed the chat over        -> open until released or 24 hours of silence
* the owner sent /bot off             -> the whole garage, until he says otherwise

Section 6 of the brief in one sentence: the bot never talks over the owner.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from .config import settings
from .db import Conversation, Garage, Handoff, SessionLocal, utcnow

log = logging.getLogger(__name__)


def ensure_garage(garage_id: str, name: str = "") -> Garage:
    with SessionLocal() as db:
        row = db.get(Garage, garage_id)
        if row is None:
            row = Garage(id=garage_id, name=name or garage_id)
            db.add(row)
            db.commit()
            db.refresh(row)
        return row


def bot_enabled(garage_id: str) -> bool:
    with SessionLocal() as db:
        row = db.get(Garage, garage_id)
        return True if row is None else bool(row.bot_enabled)


def set_bot_enabled(garage_id: str, enabled: bool) -> None:
    ensure_garage(garage_id)
    with SessionLocal() as db:
        row = db.get(Garage, garage_id)
        row.bot_enabled = enabled
        db.commit()
    log.info("bot %s for garage %s", "on" if enabled else "off", garage_id)


def open_handoff(db, conversation_id: int) -> Handoff | None:
    return (
        db.query(Handoff)
        .filter(Handoff.conversation_id == conversation_id, Handoff.released_at.is_(None))
        .order_by(Handoff.id.desc())
        .first()
    )


def is_muted(db, conv: Conversation) -> str | None:
    """Why the bot should stay quiet in this chat, or None to go ahead."""
    if not bot_enabled(conv.garage_id):
        return "bot off for this garage"
    if conv.paused_until and conv.paused_until > utcnow():
        return "owner is handling this chat"
    if open_handoff(db, conv.id):
        return "handed over, waiting for release"
    return None


def pause_for_owner(db, conv: Conversation) -> None:
    """He typed. Step back for a couple of hours without ending the handover."""
    conv.paused_until = utcnow() + timedelta(hours=settings.handoff_pause_hours)


def release(garage_id: str, number: str) -> int:
    """Give a conversation back to the bot. Returns how many were released."""
    with SessionLocal() as db:
        conv = (
            db.query(Conversation)
            .filter_by(garage_id=garage_id, customer_number=number)
            .one_or_none()
        )
        if conv is None:
            return 0

        conv.paused_until = None
        count = 0
        for row in (
            db.query(Handoff)
            .filter(Handoff.conversation_id == conv.id, Handoff.released_at.is_(None))
            .all()
        ):
            row.released_at = utcnow()
            count += 1
        db.commit()
    log.info("released %s (%d handoffs)", number, count)
    return count or 1  # the pause alone counts as a release


def hand_to_owner(garage_id: str, number: str, reason: str = "owner asked") -> None:
    """The other direction: the owner taking a chat off the bot on purpose."""
    with SessionLocal() as db:
        conv = (
            db.query(Conversation)
            .filter_by(garage_id=garage_id, customer_number=number)
            .one_or_none()
        )
        if conv is None:
            return
        if open_handoff(db, conv.id) is None:
            db.add(Handoff(garage_id=garage_id, conversation_id=conv.id, reason=reason))
        db.commit()


def auto_release_quiet_handoffs(now=None) -> int:
    """A handed-over chat comes back to the bot after 24 hours of silence.

    Silence, not elapsed time: if the owner and customer are still going back
    and forth, the bot stays out of it however long that takes.
    """
    now = now or utcnow()
    cutoff = now - timedelta(hours=settings.handoff_auto_release_hours)
    released = 0

    with SessionLocal() as db:
        rows = (
            db.query(Handoff, Conversation)
            .join(Conversation, Handoff.conversation_id == Conversation.id)
            .filter(Handoff.released_at.is_(None), Conversation.last_message_at < cutoff)
            .all()
        )
        for handoff, conv in rows:
            handoff.released_at = now
            conv.paused_until = None
            released += 1
        db.commit()

    if released:
        log.info("auto-released %d quiet handoffs", released)
    return released
