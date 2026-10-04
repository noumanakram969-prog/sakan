"""One message in, one reply out.

The shape of a turn:

    read everything the message contains  ->  qualify.extract
    decide what kind of message it is     ->  classify
    look the answer up                    ->  inventory.quote
    compose from the facts, nothing else  ->  llm
    refuse anything the facts do not back ->  guard

The composer is the only part that can be creative, and it is the only part that
is not trusted. Everything it writes passes the guard, and the guard compares
against a set of numbers assembled from the inventory file - not from the
model's output, and not from the conversation.

If the model is unavailable, or says something unsupported, the turn still ends
with a sensible message: a handover. Degrading to "an agent will call you" is
always correct; degrading to an invented price never is.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .inventory import Agency, NeedMore, Quote, allowed_numbers, find_project, quote
from .qualify import Grade, Lead, extract, grade, next_question, summary

log = logging.getLogger("sakan.engine")

# Below this the agent hands over rather than guessing which project was meant.
CONFIDENCE_FLOOR = 0.7


class Intent(str, Enum):
    PRICE = "price"
    INFO = "info"
    VIEWING = "viewing"
    ADVICE = "advice"        # "is it a good investment" - always a handover
    CHITCHAT = "chitchat"
    OTHER = "other"


# "2 bed in Palm Jumeirah" after a JVC conversation must not reuse JVC. A
# customer who names a place we do not cover and receives another area's prices
# will take those away as that area's prices.
LOCATION_PHRASE = re.compile(
    r"\b(?:in|at|near|around)\s+([A-Za-z][A-Za-z\s']{2,25})", re.I)

ADVICE_PATTERNS = [
    r"\bgood (investment|buy|deal|time)\b",
    r"\bworth (it|buying)\b",
    r"\b(roi|yield|return|appreciat|capital gain)",
    r"\bwill (it|prices?) (go up|rise|increase|drop|fall)\b",
    r"\bshould i (buy|invest)\b",
    r"\brent(al)? (income|yield)\b",
    r"\bهل .*(استثمار|مربح)",
]

VIEWING_PATTERNS = [r"\bview(ing)?\b", r"\bvisit\b", r"\bsee (the|it|unit|apartment)\b",
                    r"\bshow me around\b", r"\bsite visit\b", r"\bمعاينة\b"]

PRICE_PATTERNS = [r"\bprice\b", r"\bhow much\b", r"\bcost\b", r"\bstarting\b",
                  r"\bبكم\b", r"\bكم سعر\b", r"\bkitna\b", r"\bkitne\b"]

INFO_KEYS = {
    "payment_plan": [r"payment plan", r"installment", r"instalment", r"\bplan\b"],
    "handover": [r"handover", r"completion", r"when.*ready", r"delivery date"],
    "service_charge": [r"service charge", r"maintenance fee"],
    "fees": [r"\bfees?\b", r"dld", r"transfer fee", r"commission"],
    "mortgage": [r"mortgage", r"down ?payment", r"loan", r"finance"],
}


@dataclass
class Reply:
    text: str
    handover: bool = False
    handover_reason: str = ""
    lead: Lead = field(default_factory=Lead)
    facts: dict[str, Any] = field(default_factory=dict)
    quotes: list[Quote] = field(default_factory=list)
    intent: Intent = Intent.OTHER

    @property
    def lead_summary(self) -> str:
        return summary(self.lead)


def classify(text: str) -> Intent:
    t = text.lower()
    # Advice is checked first on purpose: "what's the ROI on a 2 bed in JVC" is
    # a price question wearing a request for regulated advice, and the advice
    # half is the one that matters.
    if any(re.search(p, t) for p in ADVICE_PATTERNS):
        return Intent.ADVICE
    if any(re.search(p, t) for p in VIEWING_PATTERNS):
        return Intent.VIEWING
    if any(re.search(p, t) for p in PRICE_PATTERNS):
        return Intent.PRICE
    for key, pats in INFO_KEYS.items():
        if any(re.search(p, t) for p in pats):
            return Intent.INFO
    if len(t.split()) <= 3 and re.search(r"\b(hi|hello|hey|salam|السلام)\b", t):
        return Intent.CHITCHAT
    return Intent.OTHER


def _info_facts(agency: Agency, text: str) -> dict[str, Any]:
    """Facts about how buying works. These are rules, not opinions, so they can
    be answered without an agent."""
    t = text.lower()
    out: dict[str, Any] = {}
    if any(re.search(p, t) for p in INFO_KEYS["fees"]):
        out["fees"] = agency.data.get("fees", {})
    if any(re.search(p, t) for p in INFO_KEYS["mortgage"]):
        out["mortgage_down_payment"] = agency.data.get("mortgage", {})
    return out


def respond(
    text: str,
    agency: Agency,
    *,
    lead: Lead | None = None,
    compose: Callable[[str, dict[str, Any]], str] | None = None,
    guard: Callable[[str, set[str], bool], Any] | None = None,
) -> Reply:
    """Produce one reply.

    `compose` and `guard` are injected so the turn can be tested against a model
    that misbehaves on purpose - which is the only interesting case.
    """
    lead = extract(text, agency, into=lead or Lead())
    intent = classify(text)

    # --- things that are always a handover, before any lookup --------------
    if intent is Intent.ADVICE:
        return Reply(
            text="That's a conversation worth having properly - one of our agents "
                 "will call you and go through the numbers.",
            handover=True, handover_reason="advice", lead=lead, intent=intent,
        )

    if intent is Intent.VIEWING:
        return Reply(
            text="Happy to arrange that. An agent will call you shortly to fix a time.",
            handover=True, handover_reason="viewing", lead=lead, intent=intent,
        )

    # --- look up what we can ----------------------------------------------
    facts: dict[str, Any] = {}
    quotes: list[Quote] = []

    # Fees and down-payment rules are facts about how buying works. They do not
    # depend on which unit anyone wants, so they are answered before anything
    # asks for a bedroom count.
    facts |= _info_facts(agency, text)

    project = find_project(agency, text)

    area = lead.area
    named = LOCATION_PHRASE.search(text)
    if named and project is None:
        from .inventory import parse_area
        here = parse_area(named.group(1), agency.areas)
        if here is None:
            area = None          # they named somewhere else - do not answer for JVC
        else:
            area = here

    if intent in (Intent.PRICE, Intent.INFO, Intent.OTHER):
        try:
            quotes = quote(
                agency,
                project_id=project["id"] if project else None,
                area=area,
                beds=lead.beds,
            )
        except NeedMore as need:
            if facts:
                # We already have something worth saying. Say it rather than
                # answering a question with a question.
                pass
            elif need.missing == "area":
                # They named somewhere we do not cover. Ask which of ours they
                # mean - not the next question on the qualification list, which
                # would ignore what they just said.
                return Reply(
                    text="We don't cover that one. Which area did you have in "
                         "mind - " + ", ".join(sorted(agency.areas.values())[:3]) + "?",
                    lead=lead, intent=intent)
            else:
                # Not a failure. Ask for the one missing thing.
                q = next_question(lead)
                question = q[1] if q else f"Which {need.missing}?"
                return Reply(text=question, lead=lead, intent=intent)

        if not quotes and not facts:
            return Reply(
                text="I don't have that one on our list - an agent will call you "
                     "and check what's available.",
                handover=True, handover_reason="no_match", lead=lead, intent=intent,
            )

        # Three is a reply; eight is a brochure.
        quotes = quotes[:3]
        if quotes:
            facts["matches"] = [q.as_facts() for q in quotes]

    if not facts:
        q = next_question(lead)
        if q:
            return Reply(text=q[1], lead=lead, intent=intent)
        return Reply(
            text="An agent will call you shortly.",
            handover=True, handover_reason="no_facts", lead=lead, intent=intent,
        )

    # --- compose, then refuse anything the facts do not support ------------
    if compose is None:
        return Reply(text=_plain(quotes, facts, intent, text), lead=lead,
                     facts=facts, quotes=quotes, intent=intent)

    try:
        draft = compose(text, facts)
    except Exception:
        log.exception("composer failed - handing over")
        return Reply(text="An agent will call you shortly.", handover=True,
                     handover_reason="composer_error", lead=lead, intent=intent)

    allowed = allowed_numbers(quotes, agency)
    if guard is not None:
        verdict = guard(draft, allowed, bool(quotes))
        if not getattr(verdict, "ok", True):
            log.warning("guard blocked a reply: %s", getattr(verdict, "reason", ""))
            return Reply(
                text="Let me have an agent confirm the exact figures and call you.",
                handover=True, handover_reason="guard_blocked",
                lead=lead, facts=facts, quotes=quotes, intent=intent,
            )

    return Reply(text=draft, lead=lead, facts=facts, quotes=quotes, intent=intent)


def _plain(quotes: list[Quote], facts: dict[str, Any] | None = None,
           asked: Intent | None = None, text: str = "") -> str:
    """The reply when no model is configured.

    Charmless, but it answers the question that was actually asked - which is
    the point. If this renderer can answer from the facts alone, the facts were
    sufficient, and anything the model adds on top is presentation rather than
    substance.
    """
    facts = facts or {}
    t = text.lower()
    lines: list[str] = []

    # Answer what they asked about this project, not the price again.
    if quotes and any(re.search(p, t) for p in INFO_KEYS["payment_plan"]):
        for q in quotes:
            if q.payment_plan:
                lines.append(f"*{q.project}* — {q.payment_plan}")
        if lines:
            return "\n".join(lines)

    if quotes and any(re.search(p, t) for p in INFO_KEYS["handover"]):
        for q in quotes:
            lines.append(f"*{q.project}* — handover {q.handover}")
        return "\n".join(lines)

    if quotes and any(re.search(p, t) for p in INFO_KEYS["service_charge"]):
        for q in quotes:
            if q.service_charge_psf:
                lines.append(f"*{q.project}* — AED {q.service_charge_psf} per sqft")
        if lines:
            return "\n".join(lines)

    if "fees" in facts:
        for name, value in facts["fees"].items():
            lines.append(f"{name.replace('_', ' ').title()}: {value}")
        return "\n".join(lines)

    if "mortgage_down_payment" in facts:
        for name, value in facts["mortgage_down_payment"].items():
            lines.append(f"{name.replace('_', ' ').title()}: {value}")
        return "\n".join(lines)

    if not quotes:
        return "An agent will call you shortly."

    for q in quotes:
        price = f"{int(q.price_from):,}"
        lines.append(f"*{q.project}*, {q.area} — {q.unit.replace('bed', ' bed')} "
                     f"from *AED {price}*")
    lines.append("Would you like an agent to send the current availability?")
    return "\n".join(lines)
