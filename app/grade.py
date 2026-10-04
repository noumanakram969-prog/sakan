"""Run the question set against the live model and score it.

The offline tests prove the guardrails hold whatever the model does. This is the
other half: whether the model reads a real customer correctly in the first
place. It costs API calls, so it is a command you run, not a test that runs
itself.

The number that matters is MISLABEL: a real price from the sheet, for the wrong
service. Nothing was invented, so the guard has no objection - only a person
comparing the reply to the sheet can catch it. Unnecessary handovers are a
nuisance; a mislabel is an argument at the counter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import engine, garages, pricing

QUESTIONS = Path(__file__).resolve().parent.parent / "tests" / "questions.yaml"

# Verdicts, worst first - the order they are reported in.
MISLABEL = "MISLABEL"
WRONG_KIND = "wrong kind of answer"
PRICED_A_SYMPTOM = "PRICED A SYMPTOM"
MISSED = "unnecessary handover"
BLOCKED = "blocked by the guard"
OK = "ok"


@dataclass
class Result:
    id: str
    verdict: str
    question: str
    reply: str
    detail: str = ""

    @property
    def bad(self) -> bool:
        return self.verdict != OK


@dataclass
class Scorecard:
    results: list[Result] = field(default_factory=list)

    def count(self, verdict: str) -> int:
        return sum(1 for r in self.results if r.verdict == verdict)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return self.count(OK)


def load_questions(path: Path | None = None) -> list[dict[str, Any]]:
    data = yaml.safe_load((path or QUESTIONS).read_text(encoding="utf-8"))
    return data.get("questions") or []


def _expected_price(garage: dict, case: dict) -> str | None:
    """What the sheet says, so a mislabel is measured against the file, not the yaml."""
    try:
        return pricing.quote(
            garage.get("prices") or {}, case.get("service_id"), case.get("category")
        ).text
    except pricing.NotOnSheet:
        return None


def judge(garage: dict, case: dict, reply: engine.Reply) -> Result:
    expect = case.get("expect")
    text = reply.text
    base = dict(id=case["id"], question=case["text"], reply=text)

    if reply.blocked is not None:
        return Result(verdict=BLOCKED, detail=str(reply.blocked.offending), **base)

    if expect == "quote":
        on_sheet = _expected_price(garage, case) or case.get("price") or ""
        if reply.quote is None:
            return Result(verdict=MISSED, detail="expected %s" % on_sheet, **base)
        if reply.quote.service_id != case.get("service_id"):
            return Result(
                verdict=MISLABEL,
                detail="quoted %s (%s) instead of %s"
                       % (reply.quote.service_id, reply.quote.display, case.get("service_id")),
                **base,
            )
        if reply.quote.category != case.get("category"):
            return Result(
                verdict=MISLABEL,
                detail="right service, wrong car class: %s not %s"
                       % (reply.quote.category, case.get("category")),
                **base,
            )
        if on_sheet and on_sheet not in text:
            return Result(verdict=WRONG_KIND, detail="price not in the reply", **base)
        return Result(verdict=OK, **base)

    if expect == "symptom":
        if reply.quote is not None:
            return Result(verdict=PRICED_A_SYMPTOM, detail=reply.quote.display, **base)
        if reply.is_handoff:
            return Result(verdict=MISSED, detail=reply.handoff_reason or "", **base)
        return Result(verdict=OK, **base)

    if expect == "info":
        if reply.is_handoff:
            return Result(verdict=MISSED, detail=reply.handoff_reason or "", **base)
        if reply.intent != "info":
            return Result(verdict=WRONG_KIND, detail="read as %s" % reply.intent, **base)
        return Result(verdict=OK, **base)

    if expect == "gather":
        # Must ask for something, and must not have quoted or booked on a guess.
        if reply.quote is not None:
            return Result(verdict=MISLABEL, detail="quoted without being told the car", **base)
        if reply.booking is not None:
            return Result(verdict=MISLABEL, detail="booked without the details", **base)
        if reply.is_handoff:
            return Result(verdict=MISSED, detail=reply.handoff_reason or "", **base)
        return Result(verdict=OK, **base)

    return Result(verdict=WRONG_KIND, detail="unknown expectation %r" % expect, **base)


def run(garage_id: str, path: Path | None = None, on_case=None) -> Scorecard:
    garage = garages.load(garage_id)
    card = Scorecard()

    for case in load_questions(path):
        reply = engine.build_reply(garage, case["text"])
        result = judge(garage, case, reply)
        card.results.append(result)
        if on_case:
            on_case(result)

    return card


def render(card: Scorecard) -> str:
    lines = ["", "%d of %d correct" % (card.passed, card.total), ""]

    for verdict in (MISLABEL, PRICED_A_SYMPTOM, BLOCKED, WRONG_KIND, MISSED):
        count = card.count(verdict)
        if count:
            lines.append("%-22s %d" % (verdict, count))

    failures = [r for r in card.results if r.bad]
    if failures:
        lines.append("")
        for r in failures:
            lines.append("%s  %s" % (r.id, r.verdict))
            lines.append("    asked: %s" % r.question)
            lines.append("    said:  %s" % r.reply.replace("\n", " ")[:110])
            if r.detail:
                lines.append("    why:   %s" % r.detail)

    if card.count(MISLABEL) or card.count(PRICED_A_SYMPTOM):
        lines += ["", "Mislabels are the ones to fix before go-live. Nothing was "
                      "invented, so no guard would have caught them."]
    return "\n".join(lines)
