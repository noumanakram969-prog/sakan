"""The 40 adversarial questions, run against a deliberately badly behaved model.

The stub composer here does the worst thing a language model can do in this
product: it invents a confident price and names a cause, every single time. The
point of these tests is that it does not matter. Nothing it writes reaches a
customer, because the price never came from it in the first place and the gate
does not let its numbers through.

What this covers: the guardrails, deterministically, with no API key.
What this does not cover: the classifier mislabelling one real service as
another. Nothing here can catch that - only the reply echoing back what it
matched lets the customer catch it. See tests/README.md.
"""
import re
from pathlib import Path

import pytest
import yaml

from app import engine

QUESTIONS = yaml.safe_load((Path(__file__).parent / "adversarial_questions.yaml").read_text(encoding="utf-8"))

MONEY = re.compile(r"(?i)\b(aed|dhs?|dirhams?)\b|د\.إ")
DIGITS = re.compile(r"\d")

# What a bad model turn looks like: a price nobody looked up, plus a diagnosis.
ROGUE_DRAFT = (
    "That is definitely your alternator. It will be around AED 950, "
    "we can do it today for 900."
)


@pytest.fixture
def rogue(monkeypatch):
    """Model that always invents. Classifier reads the message correctly."""
    def _classify(message, service_ids, history=None, **kw):
        return _classify.read

    monkeypatch.setattr(engine, "classify", _classify)
    monkeypatch.setattr(engine, "compose", lambda *a, **k: ROGUE_DRAFT)
    return _classify


@pytest.mark.parametrize("case", QUESTIONS["off_sheet"], ids=lambda c: c["id"])
def test_off_sheet_price_requests_never_produce_a_price(rogue, garage, case):
    # the honest reading: a price question for something not on this sheet
    rogue.read = {
        "intent": "price", "language": case["lang"], "service_id": None,
        "car_category": None, "confidence": 0.9,
    }
    r = engine.build_reply(garage, case["text"])

    assert r.is_handoff, "%s should have handed over" % case["id"]
    assert not DIGITS.search(r.text), "%s leaked a number: %r" % (case["id"], r.text)
    assert not MONEY.search(r.text), "%s leaked a currency: %r" % (case["id"], r.text)
    assert r.text == engine.HANDOFF[case["lang"]]


@pytest.mark.parametrize("case", QUESTIONS["symptom"], ids=lambda c: c["id"])
def test_symptom_messages_never_produce_a_price_or_a_cause(rogue, garage, case):
    rogue.read = {
        "intent": "symptom", "language": case["lang"],
        "symptom": case["text"], "confidence": 0.9,
    }
    r = engine.build_reply(garage, case["text"])

    # symptom turns have no quote, so the gate blocks the rogue draft outright
    assert r.quote is None
    assert not MONEY.search(r.text), "%s leaked a currency: %r" % (case["id"], r.text)
    assert "alternator" not in r.text.lower(), "%s leaked a diagnosis" % case["id"]


def test_the_rogue_draft_would_have_failed_without_the_gate():
    """Guard against the tests passing because the stub quietly stopped misbehaving."""
    assert MONEY.search(ROGUE_DRAFT) and "alternator" in ROGUE_DRAFT


def test_every_question_has_a_unique_id():
    ids = [c["id"] for group in QUESTIONS.values() for c in group]
    assert len(ids) == len(set(ids)) == 40
