"""Onboarding nudges to the garage owner.

Two messages, each once:
* setup reminder — signed up but hasn't finished their prices after a day.
* welcome — the moment their setup is complete ("all set, let's grow").

Both are business-initiated (the owner never messaged us), so they are approved
WhatsApp templates, sent the same way as booking reminders. Delivery therefore
depends on the templates being approved in Meta and the sending number being
live; the logic here decides who gets what and never sends twice.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from . import garages, onboard, whatsapp
from .config import settings
from .db import Owner, SessionLocal, utcnow

log = logging.getLogger(__name__)

SETUP_REMINDER_AFTER_HOURS = 24

DEFAULT_TEMPLATES = {
    "onboarding_reminder": {"name": "onboarding_reminder", "vars": ["garage", "link"]},
    "onboarding_welcome": {"name": "onboarding_welcome", "vars": ["garage"]},
}


def _prices_complete(prices: dict) -> bool:
    services = (prices or {}).get("services") or []
    if not services:
        return False
    for s in services:
        vals = ((s or {}).get("prices") or {}).values()
        if not vals or all(str(v).strip().lower() in ("", "todo", "none", "null") for v in vals):
            return False
    return True


def _has_any_price(prices: dict) -> bool:
    for s in ((prices or {}).get("services") or []):
        for v in ((s or {}).get("prices") or {}).values():
            if str(v).strip().lower() not in ("", "todo", "none", "null"):
                return True
    return False


def _garage(gid: str) -> dict | None:
    try:
        return garages.load(gid)
    except garages.GarageNotFound:
        return None


def _edit_link(gid: str) -> str:
    return "%s/onboard/%s?t=%s" % (settings.public_base_url.rstrip("/"), gid, onboard.token_for(gid))


async def _send(number: str, key: str, variables: list[str], language: str = "en") -> bool:
    spec = DEFAULT_TEMPLATES[key]
    try:
        await whatsapp.send_template(number, spec["name"], language, variables)
        return True
    except whatsapp.WhatsAppError as exc:
        log.error("%s to %s failed: %s", key, number, exc)
        return False


async def send_setup_reminders(now=None) -> int:
    """Owners who signed up a day ago and still have no prices in — nudge once."""
    now = now or utcnow()
    cutoff = now - timedelta(hours=SETUP_REMINDER_AFTER_HOURS)

    with SessionLocal() as db:
        candidates = (
            db.query(Owner)
            .filter(Owner.setup_nudged.is_(False), Owner.created_at <= cutoff)
            .all()
        )

    sent = 0
    for owner in candidates:
        g = _garage(owner.garage_id)
        if g is None or _has_any_price(g.get("prices") or {}):
            continue  # gone, or they've started — nothing to nudge
        name = (g.get("info") or {}).get("name") or owner.garage_id
        if await _send(owner.number, "onboarding_reminder", [name, _edit_link(owner.garage_id)]):
            sent += 1
        with SessionLocal() as db:  # mark whether or not it delivered — one attempt
            row = db.get(Owner, owner.id)
            if row:
                row.setup_nudged = True
                db.commit()
    if sent:
        log.info("sent %d onboarding reminders", sent)
    return sent


async def send_signup_confirmation(garage_id: str) -> None:
    """Right after an owner signs up: WhatsApp them a welcome + their setup link.
    Counts as their setup nudge, so the 24h reminder won't double up. Delivers
    once the onboarding_reminder template is approved in Meta."""
    g = _garage(garage_id)
    if g is None:
        return
    from .db import Owner, SessionLocal
    with SessionLocal() as db:
        owner = db.query(Owner).filter_by(garage_id=garage_id).first()
    if owner is None:
        return
    name = (g.get("info") or {}).get("name") or garage_id
    if await _send(owner.number, "onboarding_reminder", [name, _edit_link(garage_id)]):
        with SessionLocal() as db:
            row = db.query(Owner).filter_by(garage_id=garage_id).first()
            if row:
                row.setup_nudged = True
                db.commit()
        log.info("sent signup confirmation to owner of %s", garage_id)


async def maybe_welcome(garage_id: str) -> None:
    """Called after a save. Once the owner has entered any real price (blanks are
    allowed on purpose — they mean 'free inspection'), send the one-time 'all set'
    message. This matches what the owner sees as 'I've done my prices'."""
    g = _garage(garage_id)
    if g is None or not _has_any_price(g.get("prices") or {}):
        return
    with SessionLocal() as db:
        owner = db.query(Owner).filter_by(garage_id=garage_id).first()
        if owner is None or owner.welcomed:
            return
        number, name = owner.number, (g.get("info") or {}).get("name") or garage_id
        owner_id = owner.id

    if await _send(number, "onboarding_welcome", [name]):
        with SessionLocal() as db:
            row = db.get(Owner, owner_id)
            if row:
                row.welcomed = True
                db.commit()
        log.info("welcomed owner of %s", garage_id)
