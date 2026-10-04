"""Storage. PostgreSQL in deployment, SQLite for the tests.

One module owns the schema and the session, so swapping the backend is a
`DATABASE_URL` change and nothing else. The tests run on SQLite because a test
suite that needs a server is a test suite people stop running; the deployment
runs Postgres because the data outlives the container.

Three things live here and nowhere else:

* **The lead**, keyed by WhatsApp number. A buyer who messaged on Tuesday and
  again on Friday is one lead, not two, and the agent must not ask them their
  budget twice.
* **The conversation**, so the model has history and a human taking over can
  read what was already said.
* **The spend**, so a restart does not forget what the month has cost. A cap
  that resets on deploy is not a cap.

Every row carries `agency_id`. Multi-tenant from the first migration is cheap;
retrofitting it later means touching every query in the codebase.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


def utcnow() -> datetime:
    """UTC, stored naive.

    The columns are timezone-naive and SQLite hands back naive values, so an
    aware value here would fail the first time it was compared with one from the
    database. Everything stored is UTC by convention.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Agency(Base):
    """A brokerage. Its inventory stays in YAML, which the brokerage edits; this
    row is the tenant it all hangs off."""

    __tablename__ = "agencies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    wa_number: Mapped[str] = mapped_column(String(32), default="")
    agent_alert_number: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Lead(Base):
    """What we know about one buyer.

    Unique on (agency, number) deliberately: the same person coming back next
    week continues the same lead. Asking a returning buyer for their budget
    again is the clearest possible signal that nobody is really listening.
    """

    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("agency_id", "wa_number", name="uq_lead_agency_number"),
        Index("ix_lead_grade_seen", "agency_id", "grade", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agency_id: Mapped[str] = mapped_column(String(64), ForeignKey("agencies.id"), index=True)
    wa_number: Mapped[str] = mapped_column(String(32), index=True)

    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    budget_aed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    beds: Mapped[str | None] = mapped_column(String(16), nullable=True)
    area: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timeline: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment: Mapped[str | None] = mapped_column(String(16), nullable=True)

    grade: Mapped[str] = mapped_column(String(16), default="unqualified", index=True)
    grade_reason: Mapped[str] = mapped_column(String(200), default="")

    # Set when a human has been handed this lead, so the same lead is not
    # pushed at the sales floor twice.
    handed_over_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handover_reason: Mapped[str] = mapped_column(String(64), default="")

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Message(Base):
    """Every message, in and out.

    The agent's memory and the audit trail are the same table. When a buyer
    disputes what they were quoted, this is the answer.
    """

    __tablename__ = "messages"
    __table_args__ = (
        # Meta redelivers a webhook whenever it does not get a prompt 200, so
        # the provider's own id is the idempotency key. Without this, a slow
        # reply becomes the customer being answered three times.
        UniqueConstraint("wa_message_id", name="uq_message_wa_id"),
        Index("ix_message_lead_time", "lead_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"), index=True)
    agency_id: Mapped[str] = mapped_column(String(64), index=True)

    direction: Mapped[str] = mapped_column(String(8))          # in | out
    body: Mapped[str] = mapped_column(Text, default="")
    wa_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    intent: Mapped[str] = mapped_column(String(24), default="")
    handover: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Spend(Base):
    """One row per conversation per day.

    Daily rather than per call: the caps are daily and monthly, nobody reports
    on a single call, and a busy month then stays in the thousands of rows
    instead of the millions.
    """

    __tablename__ = "spend"
    __table_args__ = (
        UniqueConstraint("agency_id", "conversation", "day", name="uq_spend_day"),
        Index("ix_spend_month", "agency_id", "day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agency_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation: Mapped[str] = mapped_column(String(64), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)

    calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    usd: Mapped[float] = mapped_column(Float, default=0.0)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# --------------------------------------------------------------------------- engine

_is_sqlite = settings.database_url.startswith("sqlite")

connect_args = {"check_same_thread": False} if _is_sqlite else {}

# Postgres sits across a socket, so a pooled connection can be dead while the
# pool still believes in it - an idle timeout, a restart, a failover.
# pool_pre_ping spends one round trip proving the connection before handing it
# out, which is cheaper than the 500 it prevents. SQLite is a local file and
# needs none of it.
_pool_kwargs = {} if _is_sqlite else {
    "pool_pre_ping": True,
    "pool_size": settings.db_pool_size,
    "max_overflow": settings.db_max_overflow,
    "pool_recycle": 1800,
}

engine = create_engine(settings.database_url, connect_args=connect_args, **_pool_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def session():
    """Short-lived session per unit of work. The caller commits."""
    return SessionLocal()
