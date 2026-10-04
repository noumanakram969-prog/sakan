"""The grading logic, and the question set itself.

`grade` needs the live model, so it is a command rather than a test. What runs
here is everything around it: that the questions are well formed, that every
expected price still matches the demo sheet, and that a mislabel is actually
recognised as one.
"""
import pytest

from app import engine, garages, grade, pricing


@pytest.fixture(scope="module")
def demo():
    return garages.load("demo")


QUESTIONS = grade.load_questions()


# --- the question set stays in step with the sheet --------------------------

def test_there_are_thirty_questions():
    assert len(QUESTIONS) == 30


def test_every_question_has_a_unique_id_and_an_expectation():
    ids = [q["id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids))
    for q in QUESTIONS:
        assert q.get("expect") in {"quote", "info", "symptom", "gather"}, q["id"]
        assert q.get("text")
        assert q.get("lang") in {"en", "ar", "hi", "ur"}


@pytest.mark.parametrize("case", [q for q in QUESTIONS if q["expect"] == "quote"],
                         ids=lambda c: c["id"])
def test_every_expected_price_matches_the_demo_sheet(demo, case):
    """Catches the question file drifting away from prices.yaml.

    Without this, an edited sheet would quietly turn the whole set green while
    the bot answered something else entirely.
    """
    quote = pricing.quote(demo["prices"], case["service_id"], case["category"])
    assert quote.text == case["price"], case["id"]


def test_all_four_languages_are_represented():
    langs = {q["lang"] for q in QUESTIONS}
    assert langs == {"en", "ar", "hi", "ur"}


def test_the_set_covers_every_kind_of_answer():
    kinds = {q["expect"] for q in QUESTIONS}
    assert kinds == {"quote", "info", "symptom", "gather"}


# --- judging ----------------------------------------------------------------

def quote_reply(demo, service_id, category):
    q = pricing.quote(demo["prices"], service_id, category)
    return engine.Reply(text="That is AED %s." % q.text, intent="price", quote=q)


CASE = {"id": "t1", "text": "oil change camry", "expect": "quote",
        "service_id": "oil_change", "category": "sedan", "price": "180"}


def test_a_correct_quote_passes(demo):
    assert grade.judge(demo, CASE, quote_reply(demo, "oil_change", "sedan")).verdict == grade.OK


def test_the_wrong_service_is_a_mislabel(demo):
    """The failure the guard cannot catch: a real price, off the wrong row."""
    result = grade.judge(demo, CASE, quote_reply(demo, "brake_pads_front", "sedan"))
    assert result.verdict == grade.MISLABEL
    assert "brake_pads_front" in result.detail


def test_the_wrong_car_class_is_a_mislabel(demo):
    result = grade.judge(demo, CASE, quote_reply(demo, "oil_change", "luxury"))
    assert result.verdict == grade.MISLABEL
    assert "wrong car class" in result.detail


def test_a_handover_where_a_price_existed_is_a_miss(demo):
    reply = engine.Reply(text="An advisor will call.", intent="price", handoff_reason="unsure")
    assert grade.judge(demo, CASE, reply).verdict == grade.MISSED


def test_a_price_missing_from_the_text_is_flagged(demo):
    """The quote was looked up but the composer never said it."""
    q = pricing.quote(demo["prices"], "oil_change", "sedan")
    reply = engine.Reply(text="Sure, when suits you?", intent="price", quote=q)
    assert grade.judge(demo, CASE, reply).verdict == grade.WRONG_KIND


def test_pricing_a_symptom_is_its_own_verdict(demo):
    case = {"id": "t2", "text": "grinding noise", "expect": "symptom"}
    assert grade.judge(demo, case, quote_reply(demo, "brake_pads_front", "sedan")).verdict \
        == grade.PRICED_A_SYMPTOM


def test_a_symptom_answered_properly_passes(demo):
    case = {"id": "t3", "text": "grinding noise", "expect": "symptom"}
    reply = engine.Reply(text="What is the make, model and year?", intent="symptom")
    assert grade.judge(demo, case, reply).verdict == grade.OK


def test_quoting_without_being_told_the_car_is_a_mislabel(demo):
    case = {"id": "t4", "text": "how much for oil change?", "expect": "gather"}
    assert grade.judge(demo, case, quote_reply(demo, "oil_change", "sedan")).verdict \
        == grade.MISLABEL


def test_gathering_properly_passes(demo):
    case = {"id": "t5", "text": "how much for oil change?", "expect": "gather"}
    reply = engine.Reply(text="Which car is it?", intent="price")
    assert grade.judge(demo, case, reply).verdict == grade.OK


def test_a_blocked_reply_is_reported_as_blocked(demo):
    from app import guard
    reply = engine.Reply(text="advisor will call", intent="price",
                         handoff_reason="blocked: x",
                         blocked=guard.Verdict(False, "numbers", ["480"]))
    assert grade.judge(demo, CASE, reply).verdict == grade.BLOCKED


# --- the scorecard ----------------------------------------------------------

def test_the_scorecard_leads_with_the_number_that_matters(demo):
    card = grade.Scorecard(results=[
        grade.Result("q1", grade.OK, "a", "b"),
        grade.Result("q2", grade.MISLABEL, "oil change camry", "AED 950", "quoted the wrong row"),
    ])
    text = grade.render(card)
    assert "1 of 2 correct" in text
    assert "MISLABEL" in text
    assert "quoted the wrong row" in text
    assert "no guard would have caught them" in text


# --- the demo garage is genuinely complete ----------------------------------

def test_the_demo_garage_has_no_unfilled_prices(demo):
    """It exists so chat, grade and a sales demo all work with no real data."""
    for svc in demo["prices"]["services"]:
        for category in pricing.CATEGORIES:
            pricing.quote(demo["prices"], svc["id"], category)


# --- the demo garage must never answer a live number ------------------------

def test_a_live_number_is_never_routed_to_the_demo_garage():
    """Its prices are invented. Answering a real customer from them would be
    exactly the failure this whole product is built to avoid."""
    assert "demo" in garages.all_ids()
    assert "demo" not in garages.routable_ids()
    assert garages.id_for_phone_number_id("anything") != "demo"
