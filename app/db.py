"""SQLite via SQLAlchemy. Postgres later is a DATABASE_URL change, nothing else.

Every table carries garage_id — multi-garage from day one.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


def utcnow() -> datetime:
    """UTC, but naive.

    The DateTime columns are timezone-naive, and SQLite hands back naive values,
    so an aware value here would blow up the first time it met one from the
    database. Everything stored is UTC by convention.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Garage(Base):
    __tablename__ = "garages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. "care"
    name: Mapped[str] = mapped_column(String(200), default="")
    wa_phone_number_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    owner_alert_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # The owner's kill switch: /bot off from his phone stops every reply for
    # this garage until he sends /bot on. He needs a brake pedal he trusts.
    bot_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    garage_id: Mapped[str] = mapped_column(String(64), ForeignKey("garages.id"), index=True)
    customer_number: Mapped[str] = mapped_column(String(32), index=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)  # en | ar | hi | ur
    script: Mapped[str | None] = mapped_column(String(16), nullable=True)    # latin | arabic | devanagari
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    started_outside_hours: Mapped[bool] = mapped_column(Boolean, default=False)
    # bot pause — set when the owner replies from his phone, or on handoff
    paused_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index("ix_conv_garage_customer", Conversation.garage_id, Conversation.customer_number, unique=True)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    garage_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id"), index=True)
    wa_message_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    direction: Mapped[str] = mapped_column(String(8))          # in | out
    sender: Mapped[str] = mapped_column(String(16))            # customer | bot | owner
    body: Mapped[str] = mapped_column(Text, default="")
    msg_type: Mapped[str] = mapped_column(String(32), default="text")
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)  # price | booking | info | symptom | other
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    # seconds between the triggering inbound message and this outbound reply
    reply_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    garage_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id"), index=True)
    customer_name: Mapped[str] = mapped_column(String(200))
    customer_number: Mapped[str] = mapped_column(String(32))
    car: Mapped[str] = mapped_column(String(200))              # "Toyota Camry 2019"
    service: Mapped[str] = mapped_column(String(200))
    slot_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(24), default="confirmed")  # confirmed | cancelled | done
    reminder_day_before_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_morning_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    # The customer said yes to the day-before reminder. Separate from status
    # ("confirmed" there means booked): this is the human on the other end
    # promising to turn up, which is what turns an unconfirmed slot into a kept
    # one. Unset + reminded = the owner should call before the bay sits empty.
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_unconfirmed_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    # v1.1 follow-ups. Kept on the booking rather than on a customer record so
    # that "did we already message them about this?" has one obvious answer.
    followup_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    service_due_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    # Asked for a Google review after a happy post-service reply. Once, ever.
    review_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Owner(Base):
    """A garage owner's login. They sign up on the website, set a password, and
    come back anytime with their WhatsApp number + password to edit their own
    garage — no magic link to keep. One owner per garage in v1.
    """
    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    garage_id: Mapped[str] = mapped_column(String(64), index=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # normalised, no plus
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Onboarding nudges — each sent at most once so we never pester an owner.
    setup_nudged: Mapped[bool] = mapped_column(Boolean, default=False)   # "you haven't finished"
    welcomed: Mapped[bool] = mapped_column(Boolean, default=False)       # "all set" congratulations


class Lead(Base):
    """A message left on the public landing page — a garage owner asking for a
    demo. Not a customer and not tied to a garage: this is someone interested in
    Mistri itself. It lands in the admin inbox so the operator can reply now or
    whenever he next looks.
    """
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    number: Mapped[str] = mapped_column(String(32), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    handled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Handoff(Base):
    __tablename__ = "handoffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    garage_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id"), index=True)
    reason: Mapped[str] = mapped_column(String(64))            # off_sheet | unsure | owner_replied | customer_asked
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


_is_sqlite = settings.database_url.startswith("sqlite")

connect_args = {"check_same_thread": False} if _is_sqlite else {}

# Postgres sits across a socket, so a connection can be dead while the pool still
# believes in it - a firewall idle-timeout, a restart, a failover. pool_pre_ping
# spends one round trip proving the connection before handing it out, which is
# cheaper than the 500 it prevents. SQLite is a local file and needs none of it.
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
    _add_missing_columns()


def _add_missing_columns() -> None:
    """The smallest thing that stops a deploy losing data.

    There is no migration tool in v1, and create_all will not touch a table that
    already exists. So when a column is added to a model, add it to the live
    SQLite file too rather than asking anyone to delete the database - by the
    time this matters, that database is the pilot report.

    Only ever adds. Renames and drops need a real migration, and by then this
    project should have one.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = "%s %s" % (column.name, column.type.compile(engine.dialect))
                if column.default is not None and column.default.is_scalar:
                    value = column.default.arg
                    ddl += " DEFAULT %s" % (
                        int(value) if isinstance(value, bool) else repr(value)
                    )
                conn.execute(text("ALTER TABLE %s ADD COLUMN %s" % (table.name, ddl)))
