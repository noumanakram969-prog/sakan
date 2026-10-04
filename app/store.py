"""Reading and writing the things the agent remembers.

Separated from `db.py` on purpose: that file is the schema, this one is the
handful of questions the agent actually asks of it. Keeping them apart means a
query lives in one place instead of being spelled slightly differently in three.

Every function takes a session and leaves committing to the caller, so one
inbound message is one transaction. A reply that was sent but whose lead update
rolled back is the kind of inconsistency that is very hard to see later.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import func, select

from . import db
from .property.qualify import Grade, Lead as LeadState, grade as grade_lead

log = logging.getLogger("sakan.store")

# How much of the conversation the model is given. Enough to follow a thread,
# short enough that a long chat does not quietly become an expensive one.
HISTORY_TURNS = 8


def ensure_agency(s, agency_id: str, name: str = "") -> db.Agency:
    row = s.get(db.Agency, agency_id)
    if row is None:
        row = db.Agency(id=agency_id, name=name or agency_id)
        s.add(row)
        s.flush()
    return row


# --- leads ------------------------------------------------------------------

def get_or_create_lead(s, agency_id: str, wa_number: str) -> db.Lead:
    row = s.scalar(
        select(db.Lead).where(db.Lead.agency_id == agency_id, db.Lead.wa_number == wa_number)
    )
    if row is None:
        row = db.Lead(agency_id=agency_id, wa_number=wa_number)
        s.add(row)
        s.flush()
    return row


def to_state(row: db.Lead) -> LeadState:
    """Database row -> the dataclass the qualifier works with."""
    return LeadState(
        budget_aed=row.budget_aed,
        beds=row.beds,
        area=row.area,
        timeline=row.timeline,
        purpose=row.purpose,
        payment=row.payment,
        name=row.name,
    )


def save_state(s, row: db.Lead, state: LeadState) -> db.Lead:
    row.budget_aed = state.budget_aed
    row.beds = state.beds
    row.area = state.area
    row.timeline = state.timeline
    row.purpose = state.purpose
    row.payment = state.payment
    row.name = state.name

    g, reason = grade_lead(state)
    row.grade = g.value
    row.grade_reason = reason
    row.last_seen_at = db.utcnow()
    return row


def mark_handover(s, row: db.Lead, reason: str) -> bool:
    """Returns True only the first time. The sales floor should not get the
    same lead pushed at them on every subsequent message."""
    if row.handed_over_at is not None:
        return False
    row.handed_over_at = db.utcnow()
    row.handover_reason = reason
    return True


# --- messages ---------------------------------------------------------------

def already_seen(s, wa_message_id: str | None) -> bool:
    """Meta redelivers anything it did not get a prompt 200 for. The provider's
    own id is the idempotency key."""
    if not wa_message_id:
        return False
    return s.scalar(
        select(func.count()).select_from(db.Message)
        .where(db.Message.wa_message_id == wa_message_id)
    ) > 0


def record_message(
    s, lead: db.Lead, direction: str, body: str,
    *, wa_message_id: str | None = None, intent: str = "", handover: bool = False,
) -> db.Message:
    m = db.Message(
        lead_id=lead.id, agency_id=lead.agency_id, direction=direction, body=body,
        wa_message_id=wa_message_id, intent=intent, handover=handover,
    )
    s.add(m)
    return m


def history(s, lead: db.Lead, turns: int = HISTORY_TURNS) -> list[dict[str, str]]:
    """The recent conversation, oldest first, in the shape the model wants."""
    rows = s.scalars(
        select(db.Message)
        .where(db.Message.lead_id == lead.id)
        .order_by(db.Message.created_at.desc(), db.Message.id.desc())
        .limit(turns)
    ).all()
    return [
        {"role": "user" if m.direction == "in" else "assistant", "content": m.body}
        for m in reversed(rows)
    ]


# --- spend ------------------------------------------------------------------

def add_spend(
    s, agency_id: str, conversation: str, day: date,
    *, calls: int, input_tokens: int, output_tokens: int, usd: float,
) -> db.Spend:
    row = s.scalar(
        select(db.Spend).where(
            db.Spend.agency_id == agency_id,
            db.Spend.conversation == conversation,
            db.Spend.day == day,
        )
    )
    if row is None:
        row = db.Spend(agency_id=agency_id, conversation=conversation, day=day)
        s.add(row)
        s.flush()
    row.calls += calls
    row.input_tokens += input_tokens
    row.output_tokens += output_tokens
    row.usd += usd
    return row


def spend_today(s, agency_id: str, conversation: str, day: date) -> tuple[int, float]:
    row = s.scalar(
        select(db.Spend).where(
            db.Spend.agency_id == agency_id,
            db.Spend.conversation == conversation,
            db.Spend.day == day,
        )
    )
    return (row.calls, row.usd) if row else (0, 0.0)


def spend_month(s, agency_id: str, month: str) -> tuple[int, float]:
    """month as YYYY-MM."""
    start = date.fromisoformat(month + "-01")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    calls, usd = s.execute(
        select(func.coalesce(func.sum(db.Spend.calls), 0),
               func.coalesce(func.sum(db.Spend.usd), 0.0))
        .where(db.Spend.agency_id == agency_id,
               db.Spend.day >= start, db.Spend.day < end)
    ).one()
    return int(calls), float(usd)


# --- the sales floor's questions --------------------------------------------

def hot_leads(s, agency_id: str, since_hours: int = 24) -> list[db.Lead]:
    cutoff = db.utcnow() - timedelta(hours=since_hours)
    return list(s.scalars(
        select(db.Lead)
        .where(db.Lead.agency_id == agency_id,
               db.Lead.grade == Grade.HOT.value,
               db.Lead.last_seen_at >= cutoff)
        .order_by(db.Lead.last_seen_at.desc())
    ).all())


def stale_hot_leads(s, agency_id: str, older_than_hours: int = 2) -> list[db.Lead]:
    """Hot leads nobody has been handed yet.

    The job this feeds exists because the expensive failure is not a bad reply,
    it is a buyer who said "cash, this month" at 9pm and got called on Thursday.
    """
    cutoff = db.utcnow() - timedelta(hours=older_than_hours)
    return list(s.scalars(
        select(db.Lead)
        .where(db.Lead.agency_id == agency_id,
               db.Lead.grade == Grade.HOT.value,
               db.Lead.handed_over_at.is_(None),
               db.Lead.last_seen_at <= cutoff)
        .order_by(db.Lead.last_seen_at.asc())
    ).all())


def counts_by_grade(s, agency_id: str, since_hours: int = 24) -> dict[str, int]:
    cutoff = db.utcnow() - timedelta(hours=since_hours)
    rows = s.execute(
        select(db.Lead.grade, func.count())
        .where(db.Lead.agency_id == agency_id, db.Lead.last_seen_at >= cutoff)
        .group_by(db.Lead.grade)
    ).all()
    return {g: int(n) for g, n in rows}
