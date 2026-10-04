"""Lead qualification.

What the brokerage actually buys. An ad spends money to start a conversation;
this decides whether that conversation is worth an agent's afternoon, and it
does so without making the customer fill in a form.

Five things matter, in this order of usefulness to a sales floor:

    budget      what they can spend
    beds        what they want
    area        where
    timeline    when - the single strongest predictor of whether this closes
    purpose     to live in or to invest, which changes everything an agent says

The rules here are deliberately dull, because the interesting version is worse.
A score the sales team cannot predict is a score they stop trusting, and a lead
router nobody trusts gets bypassed within a week.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .inventory import Agency, parse_area, parse_beds, parse_budget


class Grade(str, Enum):
    HOT = "hot"        # agent calls today
    WARM = "warm"      # agent calls this week
    COLD = "cold"      # nurture, do not spend an agent on it
    UNQUALIFIED = "unqualified"


TIMELINE_WORDS = {
    "immediate": ["now", "asap", "immediately", "this week", "urgent", "ready to buy",
                  "this month", "حالا", "الان"],
    "3months": ["next month", "1 month", "2 month", "3 month", "soon", "quarter"],
    "6months": ["6 month", "half year", "this year", "end of year"],
    "browsing": ["just looking", "just checking", "browsing", "exploring", "curious",
                 "next year", "no rush", "in future", "maybe later"],
}

PURPOSE_WORDS = {
    "investment": ["invest", "investment", "rental", "rent out", "roi", "yield",
                   "return", "flip", "استثمار"],
    "end_use": ["live", "living", "family", "move in", "myself", "my family",
                "end user", "to stay", "سكن"],
}

CASH_WORDS = ["cash", "cash buyer", "full payment", "no mortgage", "outright"]
MORTGAGE_WORDS = ["mortgage", "loan", "finance", "bank", "emi", "installment"]


@dataclass
class Lead:
    """What we know so far. Every field optional - a conversation is not a form."""

    budget_aed: int | None = None
    beds: str | None = None
    area: str | None = None
    timeline: str | None = None
    purpose: str | None = None
    payment: str | None = None          # cash | mortgage
    name: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def known(self) -> list[str]:
        return [k for k in ("budget_aed", "beds", "area", "timeline", "purpose")
                if getattr(self, k) is not None]

    @property
    def missing(self) -> list[str]:
        return [k for k in ("budget_aed", "beds", "area", "timeline", "purpose")
                if getattr(self, k) is None]

    def as_dict(self) -> dict[str, Any]:
        return {
            "budget_aed": self.budget_aed, "beds": self.beds, "area": self.area,
            "timeline": self.timeline, "purpose": self.purpose,
            "payment": self.payment, "name": self.name,
        }


def extract(text: str, agency: Agency, into: Lead | None = None) -> Lead:
    """Read everything the message happens to contain.

    Deliberately greedy: people volunteer three things in one sentence
    ("looking for a 2 bed in JVC around 1.5m to rent out"), and asking them
    again for something they just said is the fastest way to lose the chat.
    """
    lead = into or Lead()
    t = text.lower()

    if lead.beds is None:
        lead.beds = parse_beds(text)
    if lead.area is None:
        lead.area = parse_area(text, agency.areas)
    if lead.budget_aed is None:
        b = parse_budget(text)
        # A bare "2" in "2 bed" is not a budget. Floor it at something nobody
        # types by accident.
        if b and b >= 100_000:
            lead.budget_aed = b

    if lead.timeline is None:
        for key, words in TIMELINE_WORDS.items():
            if any(w in t for w in words):
                lead.timeline = key
                break

    if lead.purpose is None:
        for key, words in PURPOSE_WORDS.items():
            if any(w in t for w in words):
                lead.purpose = key
                break

    # Not sticky: the latest explicit statement wins. Someone who asked about
    # mortgages earlier and says "cash" now is a cash buyer, and an agent ringing
    # them about financing has wasted the call.
    if any(w in t for w in CASH_WORDS):
        lead.payment = "cash"
    elif any(w in t for w in MORTGAGE_WORDS):
        lead.payment = "mortgage"

    return lead


def next_question(lead: Lead) -> tuple[str, str] | None:
    """The one thing to ask next, or None when there is enough.

    One at a time, in the order that gets a reply. Budget first is tempting for
    the sales floor and wrong for the customer - it reads as a credit check
    before hello. What they want comes first; what they can spend comes once
    they are engaged.
    """
    if lead.beds is None:
        return "beds", "What size are you looking for - studio, 1, 2 or 3 bedroom?"
    if lead.area is None:
        return "area", "Which area are you interested in?"
    if lead.budget_aed is None:
        return "budget_aed", "What budget are you working with?"
    if lead.timeline is None:
        return "timeline", "Are you looking to buy soon, or still exploring?"
    if lead.purpose is None:
        return "purpose", "Is it to live in, or as an investment?"
    return None


def grade(lead: Lead) -> tuple[Grade, str]:
    """Grade, with the reason. The reason is not decoration.

    An agent who can see why a lead was graded hot will trust the grade. One who
    cannot will work the list in whatever order they like, and the routing was
    pointless.
    """
    known = len(lead.known)

    if known <= 1:
        return Grade.UNQUALIFIED, "barely engaged"

    if lead.timeline == "browsing":
        # Browsing with real money is still worth a follow-up; browsing without
        # one is a newsletter subscriber.
        if lead.budget_aed and lead.budget_aed >= 1_000_000:
            return Grade.WARM, "exploring, but a real budget"
        return Grade.COLD, "just looking"

    if lead.timeline == "immediate":
        if lead.payment == "cash":
            return Grade.HOT, "buying now, cash"
        if lead.budget_aed:
            return Grade.HOT, "buying now, budget stated"
        return Grade.WARM, "buying now, budget unknown"

    if lead.timeline == "3months" and lead.budget_aed:
        return Grade.HOT if lead.payment == "cash" else Grade.WARM, "within 3 months"

    if known >= 4:
        return Grade.WARM, "well qualified, timeline soft"
    if known >= 2:
        return Grade.COLD, "partly qualified"
    return Grade.UNQUALIFIED, "not enough to act on"


def summary(lead: Lead) -> str:
    """The line an agent reads on their phone before calling. One line, because
    that is what gets read."""
    g, reason = grade(lead)
    bits = []
    if lead.beds:
        bits.append(lead.beds.replace("bed", " bed"))
    if lead.area:
        bits.append(lead.area.replace("_", " ").upper() if len(lead.area) <= 4
                    else lead.area.replace("_", " ").title())
    if lead.budget_aed:
        bits.append(f"AED {lead.budget_aed/1_000_000:.1f}m" if lead.budget_aed >= 1_000_000
                    else f"AED {lead.budget_aed/1000:.0f}k")
    if lead.purpose:
        bits.append("investment" if lead.purpose == "investment" else "end user")
    if lead.payment:
        bits.append(lead.payment)

    who = lead.name or "New lead"
    return f"[{g.value.upper()}] {who} - {', '.join(bits) or 'nothing stated'} ({reason})"
