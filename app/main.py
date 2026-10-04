"""FastAPI: the WhatsApp webhook, and the lead queue behind it.

The webhook does as little as possible. Meta retries anything it does not get a
200 for within seconds, so the handler verifies the signature, hands the work to
a background task and returns - a slow reply here means the same message
delivered three times, and a customer answered three times.

Conversation state is held in memory in this cut. That is a deliberate limit,
not an oversight: it keeps the repo to the part worth reading. A real
deployment swaps `_LEADS` for the brokerage's CRM, which is where their sales
floor already lives.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request, Response

from . import guard, llm, whatsapp
from .config import settings
from .property import Lead, engine, inventory, qualify

log = logging.getLogger("sakan")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

AGENCY_ID = "demo"
AGENCIES = Path("agencies")

# phone number -> what we know about them so far.
_LEADS: dict[str, Lead] = {}
_AGENCY: inventory.Agency | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _AGENCY
    _AGENCY = inventory.load(AGENCY_ID, root=AGENCIES)
    log.info("loaded agency %s with %d projects", AGENCY_ID, len(_AGENCY.projects))
    yield


app = FastAPI(title="Sakan", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "agency": AGENCY_ID,
        "projects": len(_AGENCY.projects) if _AGENCY else 0,
        "open_conversations": len(_LEADS),
    }


@app.get("/webhook")
def verify(request: Request) -> Response:
    """Meta's one-time subscription handshake."""
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == settings.meta_verify_token:
        return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def receive(request: Request, background: BackgroundTasks) -> Response:
    raw = await request.body()

    if not whatsapp.verify_signature(raw, request.headers.get("x-hub-signature-256")):
        # An unsigned request is not from Meta. 403, and nothing is parsed.
        log.warning("rejected a webhook with a bad signature")
        return Response(status_code=403)

    for msg in whatsapp.parse_webhook(await request.json()):
        background.add_task(handle, msg.from_number, msg.text)

    # 200 immediately, whatever the work turns out to be.
    return Response(status_code=200)


async def handle(number: str, text: str) -> None:
    """One inbound message, start to finish."""
    assert _AGENCY is not None

    lead = _LEADS.get(number, Lead())

    reply = engine.respond(
        text,
        _AGENCY,
        lead=lead,
        compose=_compose,
        guard=_guard,
    )
    _LEADS[number] = reply.lead

    try:
        await whatsapp.send_text(number, reply.text)
    except whatsapp.WhatsAppError:
        log.exception("could not deliver a reply to %s", number[-4:])
        return

    if reply.handover:
        # The line the sales floor actually reads. In a deployment this is the
        # CRM write, not a log line.
        log.info("HANDOVER (%s) %s", reply.handover_reason, qualify.summary(reply.lead))


def _compose(message: str, facts: dict[str, Any]) -> str:
    import json
    return llm.compose(_AGENCY.id if _AGENCY else "", json.dumps(facts, ensure_ascii=False), message)


def _guard(reply: str, allowed: set[str], money_allowed: bool):
    return guard.check(reply, allowed=allowed, money_allowed=money_allowed)
