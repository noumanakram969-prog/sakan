"""Cost control.

The failure this guards against is not a crash, it is an invoice. So the tests
are about arithmetic being right, ceilings being checked before the spend rather
than after it, and an unknown model never reporting as free.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from app import cost
from app.cost import CapExceeded, Caps, Meter


# --- pricing ----------------------------------------------------------------

def test_a_known_model_costs_what_the_price_list_says():
    # 1M in + 1M out on sonnet = 3.00 + 15.00
    assert cost.cost_usd("claude-sonnet-5", 1_000_000, 1_000_000) == pytest.approx(18.00)


def test_a_dated_snapshot_bills_at_its_family_rate():
    a = cost.cost_usd("gpt-4o-mini-2026-07-18", 1_000_000, 0)
    b = cost.cost_usd("gpt-4o-mini", 1_000_000, 0)
    assert a == b == pytest.approx(0.15)


def test_the_longest_matching_prefix_wins():
    # "gpt-4o-mini" must not be billed at the "gpt-4o" rate, which is 16x more
    assert cost.price_of("gpt-4o-mini")[0] < cost.price_of("gpt-4o")[0]


def test_an_unknown_model_is_billed_high_not_free():
    # A model that reports as free is how an overrun goes unnoticed.
    usd = cost.cost_usd("some-new-model-nobody-told-us-about", 1_000_000, 1_000_000)
    assert usd == pytest.approx(sum(cost.UNKNOWN_PRICE))
    assert usd > 0


def test_prices_can_be_overridden_from_the_environment(monkeypatch):
    monkeypatch.setenv("LLM_PRICES_JSON", json.dumps({"test-model": [1.0, 2.0]}))
    cost._load_price_overrides()
    assert cost.cost_usd("test-model", 1_000_000, 1_000_000) == pytest.approx(3.0)
    cost.PRICES.pop("test-model", None)


# --- metering ---------------------------------------------------------------

def test_a_call_is_attributed_to_the_conversation_that_caused_it():
    m = Meter()
    m.record("971500000001", "gpt-4o-mini", 1000, 500)
    m.record("971500000002", "gpt-4o-mini", 1000, 500)

    assert m.conversation("971500000001").calls == 1
    assert m.month().calls == 2


def test_the_month_total_is_the_sum_of_its_calls():
    m = Meter()
    for _ in range(4):
        m.record("x", "gpt-4o-mini", 10_000, 2_000)
    expected = 4 * cost.cost_usd("gpt-4o-mini", 10_000, 2_000)
    assert m.month().usd == pytest.approx(expected)
    assert m.month().input_tokens == 40_000


# --- caps -------------------------------------------------------------------

def test_a_runaway_conversation_is_stopped_by_call_count():
    m = Meter(Caps(calls_per_conversation_per_day=3, usd_per_conversation_per_day=99, usd_per_month=99))
    for _ in range(3):
        m.check("loop")
        m.record("loop", "gpt-4o-mini", 100, 50)

    with pytest.raises(CapExceeded) as e:
        m.check("loop")
    assert "calls per conversation" in e.value.which


def test_one_expensive_conversation_cannot_spend_the_month():
    m = Meter(Caps(usd_per_conversation_per_day=0.01, usd_per_month=99))
    m.record("whale", "claude-opus-5", 100_000, 10_000)

    with pytest.raises(CapExceeded):
        m.check("whale")
    # and everyone else is unaffected
    m.check("somebody-else")


def test_the_monthly_cap_stops_every_conversation():
    m = Meter(Caps(usd_per_month=0.001))
    m.record("a", "claude-opus-5", 100_000, 10_000)
    with pytest.raises(CapExceeded):
        m.check("b")


def test_the_cap_is_checked_before_the_spend_not_after():
    # A ceiling enforced after the call is a report, not a cap.
    m = Meter(Caps(calls_per_conversation_per_day=1))
    m.check("c")                       # allowed
    m.record("c", "gpt-4o-mini", 10, 10)
    with pytest.raises(CapExceeded):
        m.check("c")                   # refused before anything is spent
    assert m.conversation("c").calls == 1, "the refused call must not be billed"


def test_a_cap_error_says_which_ceiling_and_by_how_much():
    m = Meter(Caps(calls_per_conversation_per_day=1))
    m.record("d", "gpt-4o-mini", 10, 10)
    with pytest.raises(CapExceeded) as e:
        m.check("d")
    assert e.value.limit == 1 and e.value.used >= 1


def test_yesterdays_spend_does_not_count_against_today():
    m = Meter(Caps(calls_per_conversation_per_day=1))
    m.record("e", "gpt-4o-mini", 10, 10, today=date(2026, 10, 3))
    m.check("e", today=date(2026, 10, 4))      # must not raise


# --- reporting --------------------------------------------------------------

def test_the_report_ranks_the_costliest_conversations_and_hides_the_numbers():
    m = Meter()
    m.record("971500001111", "claude-opus-5", 100_000, 10_000)
    m.record("971500002222", "gpt-4o-mini", 100, 100)

    r = m.report()
    top = r["top_conversations"][0]
    assert top["conversation"] == "•••1111", "a spend report is not a customer list"
    assert r["total"]["calls"] == 2
    assert r["cost_per_call"] > 0


def test_the_ledger_survives_a_restart(tmp_path):
    p = tmp_path / "ledger.json"
    m1 = Meter(path=p)
    m1.record("f", "gpt-4o-mini", 10_000, 1_000)

    m2 = Meter(path=p)
    assert m2.month().calls == 1
    assert m2.month().usd == pytest.approx(m1.month().usd)


def test_a_corrupt_ledger_does_not_stop_the_agent(tmp_path):
    p = tmp_path / "ledger.json"
    p.write_text("{ this is not json", encoding="utf-8")
    m = Meter(path=p)                      # must not raise
    assert m.month().calls == 0


# --- reading the provider's own numbers -------------------------------------

class _Anthropic:
    class usage:
        input_tokens, output_tokens = 120, 45


class _OpenAI:
    class usage:
        prompt_tokens, completion_tokens = 300, 90


class _Nothing:
    pass


def test_token_counts_come_from_the_provider_not_an_estimate():
    assert cost.tokens_from_response(_Anthropic()) == (120, 45)
    assert cost.tokens_from_response(_OpenAI()) == (300, 90)


def test_a_provider_that_reports_nothing_returns_zero_rather_than_a_guess():
    # The caller logs the call as unmetered. An invented estimate would make the
    # ledger quietly disagree with the invoice.
    assert cost.tokens_from_response(_Nothing()) == (0, 0)
