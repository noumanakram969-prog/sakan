"""FastAPI app: webhook verify, webhook receive, health.

Days 1-2 scope. The webhook logs every inbound message and acks fast; reply generation
is wired in on days 3-5 via app.engine.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import BackgroundTasks, FastAPI, Request, Response
from fastapi.responses import RedirectResponse

from . import (
    admin, commands, conversations, garages, owner, privacy, respond, scheduler, slots,
    whatsapp,
)
from . import guides, onboard, owners, site
from .config import settings
from .db import Conversation, Message, SessionLocal, init_db, utcnow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("mistri")

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.enable_scheduler:
        scheduler.start()
    log.info("started, provider=%s", settings.wa_provider)
    yield
    scheduler.stop()


app = FastAPI(title="Mistri", lifespan=lifespan)
app.include_router(admin.router)
app.include_router(privacy.router)
app.include_router(onboard.router)
app.include_router(owners.router)
app.include_router(site.router)
app.include_router(guides.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "provider": settings.wa_provider}


@app.get("/webhook")
def verify(request: Request) -> Response:
    """Meta's one-time verification handshake."""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == settings.meta_verify_token
    ):
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def receive(request: Request, background: BackgroundTasks) -> Response:
    raw = await request.body()

    if not whatsapp.verify_signature(
        raw,
        request.headers.get("X-Hub-Signature-256"),
        request.query_params.get("token"),
    ):
        log.warning("rejected webhook: bad signature")
        return Response(status_code=401)

    payload = await request.json()

    for msg in whatsapp.parse_webhook(payload):
        garage_id = garages.id_for_phone_number_id(msg.phone_number_id)
        if garage_id is None:
            log.error("no garage configured for phone_number_id %r", msg.phone_number_id)
            continue

        command = _owner_command(msg, garage_id)

        try:
            recorded = _record(msg, garage_id, is_command=command is not None)
        except Exception:  # never let one bad message stop the batch
            log.exception("failed to record message %s", msg.wa_message_id)
            continue
        if recorded is None:
            continue

        # Everything below the ack: a model call is far slower than Meta's
        # webhook timeout, and a slow 200 means a redelivered message.
        if command is not None:
            background.add_task(
                owner.handle_command, command, garage_id,
                _owner_number(garage_id),
                msg.from_number if msg.sender == "owner" else None,
            )
        elif msg.sender == "customer":
            background.add_task(respond.handle, *recorded)

    # Always 200 quickly — Meta retries anything slower or non-200.
    return Response(status_code=200)


def _record(
    msg: whatsapp.InboundMessage, garage_id: str, is_command: bool = False
) -> tuple[int, str, int] | None:
    """Log every inbound message. Rule 6: the pilot report depends on this.

    Returns what respond.handle needs, or None when there is nothing to answer.
    """
    with SessionLocal() as db:

        conv = (
            db.query(Conversation)
            .filter_by(garage_id=garage_id, customer_number=msg.from_number)
            .one_or_none()
        )
        if conv is None:
            conv = Conversation(
                garage_id=garage_id,
                customer_number=msg.from_number,
                customer_name=msg.profile_name,
                started_outside_hours=_outside_hours(garage_id),
            )
            db.add(conv)
            db.flush()

        conv.last_message_at = utcnow()

        if msg.sender == "owner" and not is_command:
            # Section 6: the owner is handling this chat. The bot never talks
            # over him. A command is him talking to us, not to the customer.
            conversations.pause_for_owner(db, conv)
            log.info("owner replied to %s, bot paused", msg.from_number)

        row = Message(
            garage_id=garage_id,
            conversation_id=conv.id,
            wa_message_id=msg.wa_message_id or None,
            direction="in" if msg.sender == "customer" else "out",
            sender=msg.sender,
            body=msg.body,
            msg_type=msg.msg_type,
        )
        db.add(row)
        db.commit()
        recorded = (conv.id, garage_id, row.id)

    log.info("%s %s: %s", msg.sender, msg.from_number, msg.body[:80])
    return recorded


def _outside_hours(garage_id: str) -> bool:
    """One of the numbers the pilot report is sold on. Never let it block a reply."""
    try:
        info = garages.load(garage_id).get("info") or {}
        return slots.started_outside_hours(info, utcnow())
    except Exception:
        log.warning("could not decide opening hours for %s", garage_id)
        return False


def _owner_command(msg: whatsapp.InboundMessage, garage_id: str):
    """Is this the owner telling us something, rather than talking to a customer?"""
    if msg.sender != "owner" and msg.from_number != _owner_number(garage_id):
        return None
    return commands.parse(msg.body)


def _owner_number(garage_id: str) -> str | None:
    try:
        info = garages.load(garage_id).get("info") or {}
    except garages.GarageNotFound:
        return None
    return commands.normalise(info.get("owner_alert_number"))
