"""Catching a customer's short reply and tying it to a booking they already have.

Two things happen here, both before the normal engine runs, because both are
answers to a message *we* sent first, not fresh questions:

* No-show confirmation. The day-before reminder asks them to confirm. A "yes"
  back marks the booking confirmed, so the owner's morning list can separate the
  cars that will turn up from the ones he should ring.
* Review request. Two days after the job, the follow-up asks how it went. A warm
  reply back ("great, thanks") is the one moment they are most likely to leave a
  Google review, so that is when — and only when — we ask for one.

Neither path ever states a price or a fact from the model: the replies are fixed,
written per language here, so there is no price-safety risk and no model call.
Both fire only inside the 24-hour window (the customer just messaged us), so a
plain text reply is allowed.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from . import slots
from .db import Booking, SessionLocal, utcnow

log = logging.getLogger(__name__)

# How long after a booking a "yes" still counts as confirming it, and how long
# after a job a warm reply still counts as review-worthy.
CONFIRM_WINDOW_HOURS = 48
REVIEW_LOOKBACK_DAYS = 14

# Short affirmatives, across the four languages and their Roman forms. Kept to
# words a person sends on their own, so a real sentence is left for the engine.
_AFFIRM = {
    "yes", "yeah", "yep", "yup", "ok", "okay", "k", "sure", "confirm", "confirmed",
    "fine", "good", "done", "coming", "come", "great", "perfect",
    "haan", "han", "haa", "ha", "ji", "jee", "theek", "thik", "thike", "acha", "achha",
    "naam", "naem", "tamam", "aiwa", "aywa", "sahi",
    "نعم", "ايوة", "أيوة", "تمام", "اكيد", "أكيد", "طيب", "حاضر", "ماشي",
    "ہاں", "جی", "ٹھیک", "اچھا", "بالکل",
    "हाँ", "हां", "ठीक", "अच्छा", "जी",
}

# Warmth beyond a bare yes — the signal that they were actually happy, which is
# what a review ask should wait for.
_HAPPY = {
    "thanks", "thank", "thankyou", "great", "good", "excellent", "perfect", "amazing",
    "nice", "happy", "satisfied", "awesome", "brilliant", "best", "recommend",
    "shukran", "shukriya", "shukria", "bahut", "bohot", "zabardast", "badiya", "umda",
    "شكرا", "شكراً", "ممتاز", "رائع", "شكرًا",
    "شکریہ", "بہت", "زبردست", "اچھا",
    "धन्यवाद", "शुक्रिया", "बहुत", "बढ़िया", "शानदार",
}

_EMOJI_HAPPY = ("👍", "🙏", "😊", "❤", "🙂", "👌", "💯", "🔥")


@dataclass(frozen=True)
class After:
    """A ready reply that closes the loop, plus what it did (for the log)."""
    text: str
    action: str          # "confirmed" | "review"


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[^\s,.!?؟]+", (text or "").lower()))


def _is_affirmative(text: str) -> bool:
    body = (text or "").strip()
    if not body:
        return False
    toks = _tokens(body)
    # Short message that is essentially a yes — not a yes buried in a paragraph.
    if len(toks) <= 4 and (toks & _AFFIRM):
        return True
    return body[0] in _EMOJI_HAPPY and len(body) <= 3


def _is_happy(text: str) -> bool:
    body = (text or "").strip()
    if not body:
        return False
    if any(e in body for e in _EMOJI_HAPPY):
        return True
    return bool(_tokens(body) & _HAPPY)


# Fixed replies. No number, no fact — just the courtesy that closes the loop.
_CONFIRM_REPLY = {
    "en": "You're confirmed for {time}. See you then! 🚗",
    "ar": "تم تأكيد موعدك {time}. نراك حينها! 🚗",
    "hi": "Aapka {time} ka booking confirm ho gaya. Milte hain! 🚗",
    "ur": "Aap ka {time} ka booking confirm ho gaya. Milte hain! 🚗",
}

_REVIEW_REPLY = {
    "en": "So glad to hear it! 🙏 If you have a moment, a quick Google review really helps us:\n{link}",
    "ar": "سعداء جداً بذلك! 🙏 لو تكرمت، تقييم سريع على Google يساعدنا كثيراً:\n{link}",
    "hi": "Sun kar bahut khushi hui! 🙏 Ek chhota sa Google review hamari badi madad karega:\n{link}",
    "ur": "Yeh sun kar bohot khushi hui! 🙏 Ek chhota sa Google review hamari bari madad karega:\n{link}",
}


def _review_link(info: dict) -> str:
    link = str(info.get("review_link") or "").strip()
    if not link or link.upper().startswith("TODO") or "X" in link.upper():
        return ""
    return link


def check(garage_id: str, info: dict, customer_number: str, body: str,
          language: str | None) -> After | None:
    """Read one customer reply against their bookings. None means the normal
    engine should handle it as usual."""
    lang = language if language in _CONFIRM_REPLY else "en"
    now = utcnow()

    # 1. Confirming an upcoming, reminded, not-yet-confirmed booking.
    if _is_affirmative(body):
        with SessionLocal() as db:
            row = (
                db.query(Booking)
                .filter(
                    Booking.garage_id == garage_id,
                    Booking.customer_number == customer_number,
                    Booking.status == "confirmed",
                    Booking.confirmed.is_(False),
                    Booking.reminder_day_before_sent.is_(True),
                    Booking.slot_start >= now - timedelta(hours=2),
                    Booking.slot_start <= now + timedelta(hours=CONFIRM_WINDOW_HOURS),
                )
                .order_by(Booking.slot_start.asc())
                .first()
            )
            if row is not None:
                row.confirmed = True
                when = slots.describe(row.slot_start, info)
                db.commit()
                log.info("booking %s confirmed by customer", row.id)
                return After(_CONFIRM_REPLY[lang].format(time=when), "confirmed")

    # 2. A happy reply to the post-service follow-up → ask for a review, once.
    link = _review_link(info)
    if link and _is_happy(body):
        cutoff = now - timedelta(days=REVIEW_LOOKBACK_DAYS)
        with SessionLocal() as db:
            row = (
                db.query(Booking)
                .filter(
                    Booking.garage_id == garage_id,
                    Booking.customer_number == customer_number,
                    Booking.status != "cancelled",
                    Booking.followup_sent.is_(True),
                    Booking.review_sent.is_(False),
                    Booking.slot_start >= cutoff,
                )
                .order_by(Booking.slot_start.desc())
                .first()
            )
            if row is not None:
                row.review_sent = True
                db.commit()
                log.info("review asked for booking %s", row.id)
                return After(_REVIEW_REPLY[lang].format(link=link), "review")

    return None
