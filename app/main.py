"""FastAPI: the WhatsApp webhook, the landing page, and the operational views.

The webhook does as little as possible. Meta retries anything it does not get a
200 for within seconds, so the handler verifies the signature, hands the work to
a background task and returns - a slow reply here means the same message
delivered three times, and a customer answered three times.

Everything the agent remembers is in the database: the lead, so a buyer who
comes back next week is not asked their budget again; the conversation, which is
both the model's memory and the audit trail; and the spend, because a cap that
resets on deploy is not a cap.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request, Response
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse

from . import cost, db, guard, jobs, llm, store, whatsapp
from .config import settings
from .property import engine, inventory, qualify

log = logging.getLogger("sakan")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

AGENCY_ID = "demo"
AGENCIES = Path("agencies")

_AGENCY: inventory.Agency | None = None
_SCHED = None

# Caps are checked before each model call, so a runaway thread hands over to a
# human instead of quietly spending the month.
METER = cost.DbMeter(AGENCY_ID)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _AGENCY, _SCHED
    db.init_db()
    _AGENCY = inventory.load(AGENCY_ID, root=AGENCIES)

    with db.session() as s:
        store.ensure_agency(s, AGENCY_ID, name="Demo brokerage")
        s.commit()

    log.info("loaded agency %s with %d projects", AGENCY_ID, len(_AGENCY.projects))

    if settings.enable_scheduler:
        try:
            _SCHED = jobs.start(AGENCY_ID)
        except Exception:
            # A scheduler that will not start must not stop the agent answering
            # customers. One is a convenience, the other is the product.
            log.exception("scheduler failed to start - the agent still answers")

    yield

    if _SCHED is not None:
        _SCHED.shutdown(wait=False)


app = FastAPI(title="Sakan", lifespan=lifespan)

_LANDING = Path(__file__).parent / "static" / "landing.html"


@app.get("/", response_class=HTMLResponse)
def landing() -> HTMLResponse:
    """The page a brokerage sees. Read from disk per request rather than cached
    at import, so editing the copy does not need a restart."""
    try:
        return HTMLResponse(_LANDING.read_text(encoding="utf-8"))
    except OSError:
        return HTMLResponse("<h1>Sakan</h1><p>WhatsApp lead agent for Dubai property.</p>")


@app.get("/health")
def health() -> dict[str, Any]:
    with db.session() as s:
        counts = store.counts_by_grade(s, AGENCY_ID)
    calls, usd = _month_spend()
    return {
        "ok": True,
        "agency": AGENCY_ID,
        "projects": len(_AGENCY.projects) if _AGENCY else 0,
        "leads_24h": counts,
        "spend_this_month_usd": round(usd, 4),
        "llm_calls_this_month": calls,
        "scheduler": bool(_SCHED and _SCHED.running),
    }


@app.get("/cost")
def cost_report(month: str | None = None) -> dict[str, Any]:
    """What the agent has cost, and which conversations cost it. Numbers only -
    conversation ids are redacted to the last four digits."""
    return METER.report(month)


@app.get("/leads")
def leads(hours: int = 24) -> dict[str, Any]:
    """What the sales floor would want on their phone."""
    with db.session() as s:
        rows = store.hot_leads(s, AGENCY_ID, since_hours=hours)
        return {
            "window_hours": hours,
            "counts": store.counts_by_grade(s, AGENCY_ID, since_hours=hours),
            "hot": [
                {
                    "number": f"•••{r.wa_number[-4:]}",
                    "summary": qualify.summary(store.to_state(r)),
                    "claimed": r.handed_over_at is not None,
                    "last_seen": r.last_seen_at.isoformat(),
                }
                for r in rows
            ],
        }


class DemoTurn(BaseModel):
    """One turn of the public demo.

    The lead travels with the request rather than living in a session: the demo
    is then stateless, two people trying it at once cannot collide, and nothing
    a stranger types is written to the database.
    """

    text: str = Field(max_length=400)
    lead: dict[str, Any] = Field(default_factory=dict)


@app.post("/demo")
def demo(turn: DemoTurn) -> dict[str, Any]:
    """The agent, answering anyone who opens the page.

    No model is called here. The reply is composed from the facts alone, which
    makes the demo free to run, impossible to talk into saying something it
    should not, and an honest picture of what the system actually knows - the
    model only ever changes the wording.
    """
    assert _AGENCY is not None

    state = qualify.Lead(
        budget_aed=turn.lead.get("budget_aed"),
        beds=turn.lead.get("beds"),
        area=turn.lead.get("area"),
        timeline=turn.lead.get("timeline"),
        purpose=turn.lead.get("purpose"),
        payment=turn.lead.get("payment"),
        name=turn.lead.get("name"),
    )

    reply = engine.respond(turn.text.strip()[:400], _AGENCY, lead=state)
    g, reason = qualify.grade(reply.lead)

    return {
        "reply": reply.text,
        "handover": reply.handover,
        "handover_reason": reply.handover_reason,
        "intent": reply.intent.value,
        "lead": reply.lead.as_dict(),
        "grade": g.value,
        "grade_reason": reason,
        "summary": qualify.summary(reply.lead),
        "known": reply.lead.known,
    }


# One week of plausible ad-set numbers. Invented, and labelled as such on the
# page - the point being demonstrated is the rule engine, which is real.
_SAMPLE_ADSETS = [
    ("23851", "JVC buyers 25-45", 18400, 612, 742.0, 21, 8000),
    ("23852", "Dubai Hills 35-60", 12100, 240, 610.0, 6, 9000),
    ("23853", "Business Bay broad", 9800, 118, 388.0, 0, 6000),
    ("23854", "Retarget site 30d", 4200, 190, 96.0, 7, 4000),
]


@app.get("/demo/ads")
def demo_ads(target_cpl: float = 40.0) -> dict[str, Any]:
    """What the budget rules would do, at the target the visitor picks.

    The real `rules.evaluate` runs here. It is a pure function over rows and
    budgets, so it needs no ad account and touches nothing - which is exactly
    why deciding was separated from doing in the first place.
    """
    from .ads.insights import Row, summarise
    from .ads.rules import RuleSet, evaluate

    target_cpl = max(1.0, min(float(target_cpl), 10_000.0))

    rows = [
        Row("adset", oid, name, impressions=imp, clicks=clk, spend=spend,
            leads=leads, date_start="", date_stop="")
        for oid, name, imp, clk, spend, leads, _ in _SAMPLE_ADSETS
    ]
    budgets = {oid: budget for oid, _, _, _, _, _, budget in _SAMPLE_ADSETS}

    actions = evaluate(rows, budgets, RuleSet(target_cost_per_lead=target_cpl))

    return {
        "target_cpl": target_cpl,
        "rows": [r.as_dict() for r in sorted(
            rows, key=lambda r: (r.cost_per_lead is None, r.cost_per_lead or 0))],
        "total": summarise(rows),
        "actions": [
            {
                "verb": a.verb,
                "name": a.name,
                "reason": a.reason,
                "from": a.current_budget_minor,
                "to": a.new_budget_minor,
            }
            for a in actions
        ],
        "applied": False,
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
        log.warning("rejected a webhook with a bad signature")
        return Response(status_code=403)

    for msg in whatsapp.parse_webhook(await request.json()):
        background.add_task(handle, msg.from_number, msg.text, getattr(msg, "wa_id", None))

    return Response(status_code=200)


async def handle(number: str, text: str, wa_message_id: str | None = None) -> None:
    """One inbound message, start to finish, in one transaction.

    The reply is sent after the commit. A reply that went out while the lead
    update rolled back is the kind of inconsistency nobody finds until a
    customer points at it.
    """
    assert _AGENCY is not None

    with db.session() as s:
        if store.already_seen(s, wa_message_id):
            log.info("ignored a redelivered message %s", wa_message_id)
            return

        lead_row = store.get_or_create_lead(s, AGENCY_ID, number)
        state = store.to_state(lead_row)
        past = store.history(s, lead_row)
        store.record_message(s, lead_row, "in", text, wa_message_id=wa_message_id)

        try:
            reply = engine.respond(
                text, _AGENCY, lead=state,
                compose=lambda m, f: _compose(m, f, number, past),
                guard=_guard,
            )
        except cost.CapExceeded as over:
            # Over budget is not an error the customer should see. It is the
            # same answer as anything else the agent cannot do safely: a human.
            log.warning("cost cap hit for %s: %s", number[-4:], over)
            store.save_state(s, lead_row, state)
            store.mark_handover(s, lead_row, "cost_cap")
            s.commit()
            await _send(number, "One of our agents will call you shortly.")
            return

        store.save_state(s, lead_row, reply.lead)
        if reply.handover and store.mark_handover(s, lead_row, reply.handover_reason):
            log.info("HANDOVER (%s) %s", reply.handover_reason, qualify.summary(reply.lead))

        store.record_message(s, lead_row, "out", reply.text,
                             intent=reply.intent.value, handover=reply.handover)
        s.commit()
        text_out = reply.text

    await _send(number, text_out)


async def _send(number: str, text: str) -> None:
    try:
        await whatsapp.send_text(number, text)
    except Exception:
        log.exception("could not deliver a reply to %s", number[-4:])


def _compose(message: str, facts: dict[str, Any], conversation: str,
             history: list[dict[str, str]] | None = None) -> str:
    return llm.compose(
        _AGENCY.id if _AGENCY else "",
        json.dumps(facts, ensure_ascii=False),
        message,
        history,
        meter=METER,
        conversation=conversation,
    )


def _guard(reply: str, allowed: set[str], money_allowed: bool):
    return guard.check(reply, allowed=allowed, money_allowed=money_allowed)


def _month_spend() -> tuple[int, float]:
    with db.session() as s:
        return store.spend_month(s, AGENCY_ID, date.today().strftime("%Y-%m"))
