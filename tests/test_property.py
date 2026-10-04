"""The property agent, with the model stubbed.

Same principle as the rest of the suite: hand the code the worst plausible model
and assert the customer never sees the damage. The model here invents a price
and promises a return on every single turn, because those are the two things
that get a Dubai brokerage in trouble.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.property import engine, inventory, qualify
from app.property.inventory import NeedMore
from app.property.qualify import Grade, Lead

AGENCIES = Path(__file__).resolve().parent.parent / "agencies"


@pytest.fixture
def agency():
    return inventory.load("demo", root=AGENCIES)


# --- a model that cannot be trusted -----------------------------------------

@dataclass
class Verdict:
    ok: bool
    reason: str = ""


def liar(_text, _facts):
    """Invents a price and promises a return, every time."""
    return ("2 bed in JVC is around AED 1,250,000 and you'll see 9% rental yield, "
            "prices are going up fast.")


def honest(_text, facts):
    m = facts.get("matches", [{}])[0]
    return f"{m.get('project', '')} from AED {m.get('starting_price_aed', '')}"


def guard(reply, allowed, money_allowed):
    """Stand-in for app.guard: no number may appear that the facts do not back."""
    import re
    for n in re.findall(r"[\d,]{4,}", reply):
        if n.replace(",", "") not in allowed:
            return Verdict(False, f"unsupported number {n}")
    if not money_allowed and "AED" in reply:
        return Verdict(False, "money with no lookup")
    return Verdict(True)


# --- parsing ----------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("2 bed in jvc", "2bed"),
    ("looking for 1BHK", "1bed"),
    ("studio please", "studio"),
    ("3-bedroom villa", "3bed"),
    ("do you have 2br", "2bed"),
    ("nothing about size", None),
])
def test_bedroom_counts_as_people_actually_type_them(text, expected):
    assert inventory.parse_beds(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("budget is 1.5m", 1_500_000),
    ("around 800k", 800_000),
    ("1,200,000 max", 1_200_000),
    ("2 million", 2_000_000),
    ("no number here", None),
])
def test_budgets_however_they_are_written(text, expected):
    assert inventory.parse_budget(text) == expected


def test_a_bedroom_count_is_not_read_as_a_budget(agency):
    lead = qualify.extract("looking for 2 bed", agency)
    assert lead.beds == "2bed"
    assert lead.budget_aed is None, "'2' must not become a budget of AED 2"


def test_an_area_is_found_by_its_initials(agency):
    assert qualify.extract("anything in JVC?", agency).area == "jvc"


def test_several_facts_in_one_sentence_are_all_read(agency):
    lead = qualify.extract(
        "hi, looking for a 2 bed in JVC around 1.5m to rent out, cash, asap", agency)
    assert lead.beds == "2bed"
    assert lead.area == "jvc"
    assert lead.budget_aed == 1_500_000
    assert lead.purpose == "investment"
    assert lead.payment == "cash"
    assert lead.timeline == "immediate"


# --- inventory: a price exists or it does not -------------------------------

def test_a_price_comes_from_the_file(agency):
    q = inventory.quote(agency, area="jvc", beds="2bed")
    assert q, "JVC has 2 beds in the demo file"
    assert all(x.price_from.isdigit() for x in q)


def test_no_bedroom_count_means_ask_not_guess(agency):
    with pytest.raises(NeedMore) as e:
        inventory.quote(agency, area="jvc")
    assert e.value.missing == "beds"


def test_a_unit_type_a_project_does_not_have_is_simply_absent(agency):
    # Golf Place has 3 and 4 beds only
    q = inventory.quote(agency, project_id="emaar_golf_place", beds="studio")
    assert q == []


def test_results_are_cheapest_first(agency):
    q = inventory.quote(agency, area="jvc", beds="1bed")
    prices = [int(x.price_from) for x in q]
    assert prices == sorted(prices)


def test_the_allowed_numbers_come_only_from_the_file(agency):
    q = inventory.quote(agency, area="jvc", beds="2bed")
    allowed = inventory.allowed_numbers(q, agency)
    assert "1450000" in allowed
    assert "1250000" not in allowed, "a number nobody filed must never be allowed"


# --- the turn ---------------------------------------------------------------

def test_an_invented_price_never_reaches_the_customer(agency):
    r = engine.respond("how much is a 2 bed in JVC?", agency, compose=liar, guard=guard)
    assert "1,250,000" not in r.text
    assert "9%" not in r.text
    assert r.handover and r.handover_reason == "guard_blocked"


def test_a_request_for_investment_advice_is_always_a_handover(agency):
    for q in ["is JVC a good investment?",
              "what ROI will I get on a 2 bed?",
              "will prices go up next year?",
              "should i buy in business bay?"]:
        r = engine.respond(q, agency, compose=honest, guard=guard)
        assert r.handover, q
        assert r.handover_reason == "advice", q
        assert "%" not in r.text


def test_an_roi_question_hiding_inside_a_price_question_is_still_advice(agency):
    r = engine.respond("what's the ROI on a 2 bed in JVC and how much is it?",
                       agency, compose=honest, guard=guard)
    assert r.handover_reason == "advice"


def test_a_missing_detail_is_asked_for_one_at_a_time(agency):
    r = engine.respond("do you have anything in JVC?", agency, compose=honest, guard=guard)
    assert not r.handover
    assert r.text.count("?") == 1, "one question, not a form"


def test_a_real_question_is_answered_from_the_file(agency):
    r = engine.respond("price of 2 bed in jvc", agency)
    assert "1,450,000" in r.text
    assert "Binghatti Aurora" in r.text


def test_a_reply_says_what_it_matched_before_the_price(agency):
    r = engine.respond("2 bed jvc price", agency)
    first = r.text.splitlines()[0]
    assert first.index("Binghatti") < first.index("AED")


def test_at_most_three_options_are_offered(agency):
    r = engine.respond("1 bed jvc price", agency)
    assert len(r.quotes) <= 3


def test_an_area_we_do_not_cover_never_gets_another_areas_prices(agency):
    # Answering "2 bed in Palm Jumeirah" with JVC numbers is the quiet failure
    # worth guarding: the customer would take those prices away as Palm prices.
    r = engine.respond("price for 2 bed in Palm Jumeirah", agency, compose=honest, guard=guard)
    assert r.quotes == []
    assert "AED" not in r.text
    assert "area" in r.text.lower()


def test_a_viewing_request_goes_to_a_human(agency):
    r = engine.respond("can I view it tomorrow?", agency, compose=honest, guard=guard)
    assert r.handover and r.handover_reason == "viewing"


def test_a_broken_model_becomes_a_handover_not_a_crash(agency):
    def explode(_t, _f):
        raise RuntimeError("API down")

    r = engine.respond("2 bed jvc price", agency, compose=explode, guard=guard)
    assert r.handover and r.handover_reason == "composer_error"
    assert "AED" not in r.text


def test_the_fallback_reply_still_carries_only_real_numbers(agency):
    r = engine.respond("2 bed jvc", agency)        # no model at all
    allowed = inventory.allowed_numbers(r.quotes, agency)
    import re
    for n in re.findall(r"[\d,]{4,}", r.text):
        assert n.replace(",", "") in allowed


def test_fees_are_answered_because_they_are_rules_not_opinions(agency):
    r = engine.respond("what are the DLD fees?", agency)
    assert "fees" in r.facts


# --- qualification ----------------------------------------------------------

def test_a_buyer_ready_now_with_cash_is_hot():
    lead = Lead(budget_aed=1_500_000, beds="2bed", area="jvc",
                timeline="immediate", payment="cash")
    g, _ = qualify.grade(lead)
    assert g is Grade.HOT


def test_someone_just_looking_is_not_hot_however_much_else_they_said():
    lead = Lead(budget_aed=900_000, beds="2bed", area="jvc",
                timeline="browsing", purpose="investment")
    g, reason = qualify.grade(lead)
    assert g is Grade.COLD and "looking" in reason


def test_browsing_with_a_real_budget_is_still_worth_a_follow_up():
    lead = Lead(budget_aed=3_000_000, beds="3bed", timeline="browsing")
    g, _ = qualify.grade(lead)
    assert g is Grade.WARM


def test_a_one_word_message_does_not_qualify_anyone():
    g, _ = qualify.grade(Lead(beds="2bed"))
    assert g is Grade.UNQUALIFIED


def test_what_they_want_is_asked_before_what_they_can_spend():
    # Budget first reads as a credit check before hello.
    assert qualify.next_question(Lead())[0] == "beds"
    assert qualify.next_question(Lead(beds="2bed"))[0] == "area"
    assert qualify.next_question(Lead(beds="2bed", area="jvc"))[0] == "budget_aed"


def test_a_fully_qualified_lead_is_asked_nothing_more():
    lead = Lead(budget_aed=1_000_000, beds="2bed", area="jvc",
                timeline="immediate", purpose="end_use")
    assert qualify.next_question(lead) is None


def test_the_agent_sees_one_line_with_the_reason():
    lead = Lead(budget_aed=1_500_000, beds="2bed", area="jvc",
                timeline="immediate", payment="cash", name="Ahmed")
    s = qualify.summary(lead)
    assert s.startswith("[HOT]") and "Ahmed" in s and "1.5m" in s and "cash" in s


def test_a_new_area_mid_conversation_does_not_reuse_the_old_one(agency):
    lead = qualify.extract("2 bed in JVC", agency)
    r = engine.respond("and in Palm Jumeirah?", agency, lead=lead)
    assert r.quotes == [], "JVC prices must not be offered as Palm prices"
    assert "AED" not in r.text


def test_cash_stated_later_overrides_an_earlier_mortgage_question(agency):
    lead = qualify.extract("what down payment for a mortgage?", agency)
    assert lead.payment == "mortgage"
    lead = qualify.extract("actually I'm paying cash", agency, into=lead)
    assert lead.payment == "cash"
