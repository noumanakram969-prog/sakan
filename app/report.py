"""The pilot report - the anti-hype test from section 7 of the brief.

This is the number that sells garage number two. Not "AI will transform your
business", but "here is what happened at Care over thirty days". Everything
here is a plain query over what was logged; nothing is estimated, and a figure
that cannot be computed is shown as such rather than filled in.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .db import Booking, Conversation, Handoff, Message, SessionLocal


@dataclass
class Report:
    garage_id: str
    start: datetime
    end: datetime
    conversations: int = 0
    conversations_outside_hours: int = 0
    price_questions: int = 0
    bookings: int = 0
    bookings_cancelled: int = 0
    handoffs: int = 0
    handoffs_open: int = 0
    replies_sent: int = 0
    replies_blocked: int = 0
    median_reply_seconds: float | None = None
    languages: dict[str, int] = field(default_factory=dict)

    @property
    def days(self) -> int:
        return max(1, (self.end - self.start).days)

    @property
    def outside_hours_share(self) -> float:
        return self.conversations_outside_hours / self.conversations if self.conversations else 0.0

    @property
    def booking_rate(self) -> float:
        return self.bookings / self.conversations if self.conversations else 0.0


def build(garage_id: str, start: datetime, end: datetime) -> Report:
    r = Report(garage_id=garage_id, start=start, end=end)

    with SessionLocal() as db:
        convs = (
            db.query(Conversation)
            .filter(
                Conversation.garage_id == garage_id,
                Conversation.started_at >= start,
                Conversation.started_at < end,
            )
            .all()
        )
        r.conversations = len(convs)
        r.conversations_outside_hours = sum(1 for c in convs if c.started_outside_hours)
        for c in convs:
            key = c.language or "unknown"
            r.languages[key] = r.languages.get(key, 0) + 1

        bot_messages = (
            db.query(Message)
            .filter(
                Message.garage_id == garage_id,
                Message.sender == "bot",
                Message.created_at >= start,
                Message.created_at < end,
            )
            .all()
        )
        r.replies_sent = len(bot_messages)
        r.price_questions = sum(1 for m in bot_messages if m.intent == "price")

        times = [m.reply_seconds for m in bot_messages if m.reply_seconds is not None]
        r.median_reply_seconds = round(statistics.median(times), 1) if times else None

        bookings = (
            db.query(Booking)
            .filter(
                Booking.garage_id == garage_id,
                Booking.created_at >= start,
                Booking.created_at < end,
            )
            .all()
        )
        r.bookings = sum(1 for b in bookings if b.status != "cancelled")
        r.bookings_cancelled = sum(1 for b in bookings if b.status == "cancelled")

        handoffs = (
            db.query(Handoff)
            .filter(
                Handoff.garage_id == garage_id,
                Handoff.created_at >= start,
                Handoff.created_at < end,
            )
            .all()
        )
        r.handoffs = len(handoffs)
        r.handoffs_open = sum(1 for h in handoffs if h.released_at is None)
        r.replies_blocked = sum(1 for h in handoffs if (h.reason or "").startswith("blocked:"))

    return r


LANGUAGE_NAMES = {"en": "English", "ar": "Arabic", "hi": "Hindi", "ur": "Urdu"}


def render(r: Report) -> str:
    """Plain text, because it gets pasted into a WhatsApp message to a garage owner."""
    lines = [
        "%s - %s to %s (%d days)" % (
            r.garage_id, r.start.date().isoformat(), (r.end - timedelta(days=1)).date().isoformat(), r.days,
        ),
        "",
        "Conversations          %d" % r.conversations,
        "  started after hours  %d (%d%%)" % (
            r.conversations_outside_hours, round(r.outside_hours_share * 100),
        ),
        "Price questions        %d" % r.price_questions,
        "Bookings               %d" % r.bookings,
    ]
    if r.bookings_cancelled:
        lines.append("  cancelled            %d" % r.bookings_cancelled)
    lines += [
        "Handed to a human      %d" % r.handoffs,
    ]
    if r.handoffs_open:
        lines.append("  still open           %d" % r.handoffs_open)
    if r.replies_blocked:
        # Not a vanity metric: every one of these is a reply the guard stopped.
        lines.append("  of which blocked     %d" % r.replies_blocked)

    lines += [
        "Replies sent           %d" % r.replies_sent,
        "Median reply time      %s" % (
            "%.1fs" % r.median_reply_seconds if r.median_reply_seconds is not None else "no data",
        ),
        "",
        "Languages",
    ]
    if r.languages:
        for code, count in sorted(r.languages.items(), key=lambda kv: -kv[1]):
            lines.append("  %-20s %d" % (LANGUAGE_NAMES.get(code, code), count))
    else:
        lines.append("  no data")

    if r.conversations:
        lines += [
            "",
            "%d in %d conversations turned into a booking (%d%%)." % (
                r.bookings, r.conversations, round(r.booking_rate * 100),
            ),
        ]
    return "\n".join(lines)


def parse_day(value: str, end_of_day: bool = False) -> datetime:
    day = date.fromisoformat(value)
    return datetime.combine(day + timedelta(days=1) if end_of_day else day, time.min)
