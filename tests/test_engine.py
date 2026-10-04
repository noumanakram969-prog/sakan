"""The whole turn, with the model stubbed out.

These tests do not need an API key. They exist to prove the parts around the
model, which is exactly where the guarantees live.
"""
import pytest

from app import engine
from app.llm import LLMUnavailable


def stub(monkeypatch, read=None, draft="ok", classify_raises=None, compose_raises=None):
    def _classify(message, service_ids, history=None, **kw):
        if classify_raises:
            raise classify_raises
        return read or {}

    def _compose(name, facts, message, history=None, **kw):
        if compose_raises:
            raise compose_raises
        return draft(facts) if callable(draft) else draft

    monkeypatch.setattr(engine, "classify", _classify)
    monkeypatch.setattr(engine, "compose", _compose)


PRICE_READ = {
    "intent": "price", "language": "en", "service_id": "oil_change",
    "car_category": "sedan", "car_make": "Toyota", "car_model": "Camry",
    "car_year": "2019", "confidence": 0.95,
}


# --- the happy path ---------------------------------------------------------

def test_a_price_on_the_sheet_is_answered(monkeypatch, garage):
    stub(monkeypatch, PRICE_READ, "Oil change, Camry 2019 - AED 180. When suits you?")
    r = engine.build_reply(garage, "oil change for my camry 2019?")
    assert not r.is_handoff
    assert r.quote.text == "180"
    assert "180" in r.text


def test_the_price_reply_uses_the_exact_sheet_price(monkeypatch, garage):
    # Price replies are built in code from the sheet, not written by the model,
    # so the price is always exact and the layout is always the same.
    stub(monkeypatch, PRICE_READ, "the model output is ignored on a price turn")
    r = engine.build_reply(garage, "oil change camry?")
    assert not r.is_handoff
    assert r.quote.display in r.text            # exact sheet price
    assert "Oil change" in r.text               # the matched service, in words
    assert "the model output" not in r.text     # the model did not write this


# --- rule 1: never invent a price -------------------------------------------

def test_off_sheet_price_is_never_leaked(monkeypatch, garage):
    # Off-sheet car work is answered naturally (offer an inspection), but if the
    # model tries to state a price the guard blocks it — it never reaches anyone.
    stub(monkeypatch, dict(PRICE_READ, service_id="gearbox_rebuild"), "AED 3000")
    r = engine.build_reply(garage, "how much to rebuild my gearbox?")
    assert "3000" not in r.text


def test_an_unfilled_price_offers_an_inspection_never_a_price(monkeypatch, garage):
    # The luxury brake price is still TODO on the sheet. We must not invent one —
    # instead offer a free inspection (natural), not a cold handover.
    stub(monkeypatch, dict(PRICE_READ, service_id="brake_pads_front", car_category="luxury"),
         "We'd need to check it — free inspection?")
    r = engine.build_reply(garage, "brake pads for my Range Rover?")
    assert not r.is_handoff
    assert r.quote is None


def test_a_vague_short_price_asks_which_service(monkeypatch, garage):
    """"how much?" with no service -> ask which service, not hand over."""
    stub(monkeypatch, {"intent": "price", "language": "en", "service_id": None,
                       "confidence": 0.9}, "ignored")
    r = engine.build_reply(garage, "how much?")
    assert not r.is_handoff
    assert "service" in r.text.lower()


def test_a_longer_off_sheet_price_offers_an_inspection(monkeypatch, garage):
    """Off-sheet car work is answered naturally — offer a free inspection, never a
    cold 'advisor will call', and never a price."""
    seen = {}
    stub(monkeypatch, {"intent": "price", "language": "en", "service_id": None, "confidence": 0.9},
         lambda f: seen.setdefault("facts", f) or "We'd need to look at it — free inspection?")
    r = engine.build_reply(garage, "how much to rebuild my gearbox please")
    assert not r.is_handoff
    assert r.quote is None
    assert "FREE inspection" in seen["facts"]


def test_a_price_with_no_car_asks_for_the_car(monkeypatch, garage):
    """Service known, car unknown -> ask which car, do NOT hand over."""
    stub(monkeypatch, dict(PRICE_READ, car_category=None, car_make=None, car_model=None),
         "ignored")
    r = engine.build_reply(garage, "how much for oil change?")
    assert not r.is_handoff
    assert r.quote is None
    assert "car" in r.text.lower()          # asks for their car


def test_a_partial_car_asks_for_the_missing_part_not_a_repeat(monkeypatch, garage):
    """They gave only the make -> name it back and ask for model/year, not repeat."""
    stub(monkeypatch, dict(PRICE_READ, car_category=None, car_make="Toyota", car_model=None),
         "ignored")
    r = engine.build_reply(garage, "toyota")
    assert not r.is_handoff and r.quote is None
    assert "Toyota" in r.text                       # acknowledges what they gave
    assert r.text != engine._ASK_CAR["en"]          # not the identical first question
    assert "year" not in r.text.lower()             # we never demand the year to quote


def test_low_confidence_never_quotes(monkeypatch, garage):
    stub(monkeypatch, dict(PRICE_READ, confidence=0.4), "AED 180")
    r = engine.build_reply(garage, "how much for the thing on my car")
    assert r.is_handoff and r.quote is None


def test_the_price_reply_ignores_a_model_that_would_invent_a_price(monkeypatch, garage):
    """Even if the model would say 480, the price reply is built from the sheet
    (180), so an invented figure can never reach the customer."""
    stub(monkeypatch, PRICE_READ, "Oil change is AED 480, best price in Dubai.")
    r = engine.build_reply(garage, "oil change camry 2019?")
    assert not r.is_handoff
    assert "180" in r.text and "480" not in r.text


def test_a_composer_that_talks_money_with_no_quote_is_blocked(monkeypatch, garage):
    stub(monkeypatch, {"intent": "greeting", "language": "en"}, "Hello! Oil changes start from AED 150.")
    r = engine.build_reply(garage, "hi")
    assert r.is_handoff and "150" not in r.text


# --- rule 2: never diagnose -------------------------------------------------

def test_a_symptom_is_never_priced(monkeypatch, garage):
    stub(monkeypatch,
         {"intent": "symptom", "language": "en", "symptom": "grinding noise when braking",
          "confidence": 0.9},
         "Sorry to hear that. What is the make, model and year?")
    r = engine.build_reply(garage, "grinding noise when I brake")
    assert not r.is_handoff
    assert r.quote is None


def test_a_symptom_reply_cannot_carry_a_price(monkeypatch, garage):
    """Even if the composer tries. money_allowed is False for a symptom turn."""
    stub(monkeypatch,
         {"intent": "symptom", "language": "en", "symptom": "noise", "confidence": 0.9},
         "Sounds like your brake pads. Around AED 400 to fix.")
    r = engine.build_reply(garage, "there is a noise")
    assert r.is_handoff and "400" not in r.text


def test_symptom_facts_forbid_diagnosis(monkeypatch, garage):
    seen = {}
    stub(monkeypatch,
         {"intent": "symptom", "language": "en", "symptom": "smoke", "confidence": 0.9},
         lambda facts: seen.setdefault("facts", facts) or "What car is it?")
    engine.build_reply(garage, "white smoke from exhaust")
    assert "may not name a cause" in seen["facts"]
    assert "may not give any price" in seen["facts"]


# --- info -------------------------------------------------------------------

@pytest.mark.parametrize("topic,needle", [
    ("location", "Al Quoz"),
    ("payment", "card"),
    ("warranty", "6 months"),
    ("pickup", "10 km"),
])
def test_info_answers_come_from_the_files(monkeypatch, garage, topic, needle):
    seen = {}
    stub(monkeypatch,
         {"intent": "info", "language": "en", "info_topic": topic, "confidence": 0.9},
         lambda facts: seen.setdefault("facts", facts) or "Here you go.")
    r = engine.build_reply(garage, "question")
    assert not r.is_handoff
    assert needle in seen["facts"]


def test_unknown_info_topic_hands_over(monkeypatch, garage):
    stub(monkeypatch, {"intent": "info", "language": "en", "info_topic": "financing", "confidence": 0.9})
    assert engine.build_reply(garage, "do you do financing?").is_handoff


# --- universal policy questions (answered, never handed over, never priced) --

@pytest.mark.parametrize("message,topic", [
    ("Can you give me a quotation before starting repairs?", "quotation"),
    ("Is your quotation inclusive of labour, parts and VAT?", "quotation"),
    ("Do I need an appointment, or can I come directly?", "appointment"),
    ("How long will the repair take?", "turnaround"),
    ("Can you finish the work today?", "turnaround"),
    ("Can you send me photos or videos of the problem?", "media"),
])
def test_common_policy_questions_route_to_a_topic(message, topic):
    assert engine._guess_info_topic(message) == topic


@pytest.mark.parametrize("message", [
    "Can you give me a quotation before starting repairs?",
    "Do I need an appointment, or can I come directly?",
    "How long will the repair take?",
    "Can you send me photos of the problem?",
])
def test_policy_questions_are_answered_not_handed_over(monkeypatch, garage, message):
    # classifier tags it "other" — the keyword fallback must still answer, with
    # no handover and no invented price.
    seen = {}
    stub(monkeypatch, {"intent": "other", "language": "en", "confidence": 0.9},
         lambda facts: seen.setdefault("facts", facts) or "Sure — here's how that works.")
    r = engine.build_reply(garage, message)
    assert not r.is_handoff
    assert seen.get("facts")            # a real fact was supplied to the composer


@pytest.mark.parametrize("message,mislabel", [
    ("Can you give me a quotation before starting repairs?", "price"),
    ("How long will the repair take?", "price"),
    ("Can you finish the work today?", "booking"),
    ("Do I need an appointment, or can I come directly?", "booking"),
])
def test_policy_questions_win_even_when_misread_as_price_or_booking(monkeypatch, garage, message, mislabel):
    # The real-world failure: the classifier tags a policy question as price or
    # booking, which used to hand over / ask "which service". The in-code policy
    # check must intercept and answer it — never a handover, never a price.
    seen = {}
    stub(monkeypatch,
         {"intent": mislabel, "language": "en", "confidence": 0.9},   # no service_id
         lambda facts: seen.setdefault("facts", facts) or "Here's how that works.")
    r = engine.build_reply(garage, message, conversation_id=1, customer_number="971500000000")
    assert not r.is_handoff
    assert r.intent == "info"
    assert r.quote is None


@pytest.mark.parametrize("message,topic", [
    ("پہلے گاڑی چیک کرکے ٹوٹل خرچہ بتا دیں، پھر کام شروع کیجیے گا۔", "quotation"),
    ("اگر صبح گاڑی دے دوں تو کب تک واپس مل جائے گی؟", "turnaround"),
    ("گاڑی لانے سے پہلے آواز کی ویڈیو بھیج دوں؟", "media"),
])
def test_urdu_policy_questions_route_deterministically(message, topic):
    assert engine._guess_policy_topic(message) == topic


@pytest.mark.parametrize("message,topic", [
    ("کیا آپ میرے آفس سے گاڑی لے کر آج ہی واپس دے سکتے ہیں؟", "pickup"),
    ("آپ کے کھلنے کے اوقات کیا ہیں؟", "hours"),
    ("کیا آپ کارڈ لیتے ہیں یا صرف کیش؟", "payment"),
    ("آپ کی وارنٹی کتنی ہے؟", "warranty"),
])
def test_urdu_info_questions_route_deterministically(message, topic):
    # pickup/hours/payment/warranty must be caught in Urdu script too, not left
    # to the classifier alone.
    assert engine._guess_policy_topic(message) is None      # not a policy topic
    assert engine._guess_info_topic(message) == topic


@pytest.mark.parametrize("message,mislabel", [
    # "quote before you start" read as price-with-a-service, and "send a video"
    # read as a symptom (it mentions a noise). Both must still answer as policy.
    ("Please give me the total before starting the work.", "price"),
    ("There's a noise — can I send you a video first?", "symptom"),
])
def test_quote_and_media_override_even_a_service_or_symptom_read(monkeypatch, garage, message, mislabel):
    read = {"intent": mislabel, "language": "en", "confidence": 0.9,
            "service_id": "oil_change", "car_make": "Toyota", "symptom": "noise"}
    stub(monkeypatch, read, lambda facts: "Here's how that works.")
    r = engine.build_reply(garage, message, conversation_id=1, customer_number="971500000000")
    assert not r.is_handoff
    assert r.intent == "info"
    assert r.quote is None


def test_a_full_service_ask_is_answered_naturally_not_handed_over(monkeypatch, garage):
    # "full service" isn't a single item on the sheet. Instead of a cold handover,
    # the model answers naturally (no price) and is given the real service list.
    seen = {}
    stub(monkeypatch,
         {"intent": "price", "language": "en", "confidence": 0.9},   # no service_id
         lambda facts: seen.setdefault("facts", facts) or "We can do oil, brakes, and more — want a free inspection?")
    r = engine.build_reply(garage, "how much for a full service on my Corolla?")
    assert not r.is_handoff                       # not a dead "advisor will call"
    assert r.quote is None                        # no price object
    assert "jobs we can price" in seen["facts"]
    assert "MUST NOT" in seen["facts"]            # the no-price rule is passed to the model


def test_an_off_sheet_job_offers_an_inspection_not_a_cold_handover(monkeypatch, garage):
    # Car work we can't price is answered naturally with a free-inspection offer —
    # no price, no dead "advisor will call".
    stub(monkeypatch, {"intent": "price", "language": "en", "confidence": 0.9},
         "We'd need to inspect it first — shall I book a free inspection?")
    r = engine.build_reply(garage, "how much to rebuild my gearbox and turbo?")
    assert not r.is_handoff and r.quote is None


def test_a_full_service_answer_cannot_carry_a_price(monkeypatch, garage):
    # Even on the natural package answer, the guard blocks an invented number.
    stub(monkeypatch, {"intent": "price", "language": "en", "confidence": 0.9},
         "A full service is about AED 900.")
    r = engine.build_reply(garage, "what packages do you offer?")
    assert r.is_handoff and "900" not in r.text   # blocked, not leaked


def test_it_does_not_repeat_the_whole_picker_when_times_already_shown(monkeypatch, garage):
    # Times already on screen (prev assistant turn ended with 👇). The customer
    # re-states the car -> nudge to the buttons, don't repeat the whole pitch.
    hist = [{"role": "user", "content": "engine noise"},
            {"role": "assistant", "content": "Let's book you a free inspection. Which time suits? Tap one below 👇"}]
    stub(monkeypatch, {"intent": "symptom", "language": "en", "confidence": 0.9,
                       "car_make": "Toyota", "car_model": "Corolla", "car_year": "2019"})
    r = engine.build_reply(garage, "Toyota Corolla 2019", hist,
                           conversation_id=1, customer_number="971500000000")
    assert r.slot_buttons                          # times still offered
    assert "free inspection" not in r.text.lower() # NOT the whole pitch again
    assert "above" in r.text.lower()               # a short nudge to the buttons


def test_a_priced_service_is_not_hijacked_by_a_policy_word(monkeypatch, garage):
    # Guard the other side: a real price request that happens to contain "how
    # long" must still be treated as a price, not the turnaround answer.
    stub(monkeypatch, {"intent": "price", "language": "en", "service_id": "oil_change",
                       "car_category": "sedan", "car_make": "Toyota", "car_model": "Camry",
                       "confidence": 0.95}, "unused")
    r = engine.build_reply(garage, "oil change for a Camry, and how long will it take?")
    assert r.quote is not None and "180" in r.text


# --- rule 3 and 4: handoff, and language ------------------------------------

def test_model_failure_hands_over_rather_than_guessing(monkeypatch, garage):
    stub(monkeypatch, classify_raises=LLMUnavailable("no key"))
    r = engine.build_reply(garage, "anything")
    assert r.is_handoff and r.text == engine.HANDOFF["en"]


def test_composer_failure_hands_over(monkeypatch, garage):
    # On a model-driven turn (a greeting here), a composer failure hands over.
    # Price turns no longer use the composer, so they are covered separately.
    stub(monkeypatch, {"intent": "greeting", "language": "en", "confidence": 0.9},
         compose_raises=LLMUnavailable("timeout"))
    assert engine.build_reply(garage, "hi there").is_handoff


@pytest.mark.parametrize("language", ["ar", "hi", "ur"])
def test_handoff_speaks_the_customers_language(monkeypatch, garage, language):
    stub(monkeypatch, {"intent": "other", "language": language, "confidence": 0.9})
    r = engine.build_reply(garage, "...")
    assert r.text == engine.HANDOFF[language]


def test_a_garage_can_override_the_handoff_line(monkeypatch, garage):
    garage["info"]["handoff_line"] = {"en": "Ali will call you in 5 minutes."}
    stub(monkeypatch, {"intent": "other", "language": "en", "confidence": 0.9})
    assert engine.build_reply(garage, "...").text == "Ali will call you in 5 minutes."


# --- messages the bot cannot read -------------------------------------------

@pytest.mark.parametrize("msg_type,expected", [
    ("image", "a photo"),
    ("audio", "a voice note"),
    ("voice", "a voice note"),
    ("video", "a video"),
    ("document", "a document"),
    ("location", "a location"),
])
def test_media_is_handed_over_not_guessed_at(monkeypatch, garage, msg_type, expected):
    """A photo of a part or a voice note about a noise. Very common in a garage."""
    stub(monkeypatch, PRICE_READ, "Sure, that is AED 180.")
    r = engine.build_reply(garage, "", msg_type=msg_type)
    assert r.is_handoff and expected in r.handoff_reason
    assert r.text == engine.MEDIA_ACK["en"]
    assert "180" not in r.text


def test_media_never_reaches_the_model(monkeypatch, garage):
    """No classify call, so no chance to guess what a photo shows."""
    called = []
    monkeypatch.setattr(engine, "classify", lambda *a, **k: called.append(1) or {})
    engine.build_reply(garage, "", msg_type="image")
    assert called == []


def test_media_is_acknowledged_in_the_language_already_in_use(monkeypatch, garage):
    r = engine.build_reply(garage, "", msg_type="image", language_hint="ar")
    assert r.text == engine.MEDIA_ACK["ar"]


def test_an_empty_text_message_is_handed_over(monkeypatch, garage):
    """A sticker or a blank message. Nothing to answer, so do not pretend."""
    stub(monkeypatch, PRICE_READ, "AED 180")
    r = engine.build_reply(garage, "   ")
    assert r.is_handoff


# --- a price the customer supplied is not a price -------------------------

def test_a_price_the_customer_suggested_cannot_be_repeated(monkeypatch, garage):
    """"My friend said you did it for 450" must not become the quote.

    The number is in the customer's message, so a naive allowlist would let it
    through looking exactly like a figure off the sheet. The sheet says 180.
    """
    stub(monkeypatch, PRICE_READ, "Oil change, Camry 2019 - AED 450. When suits you?")
    r = engine.build_reply(garage, "oil change camry 2019, my friend paid 450, same for me?")
    # The reply is built from the sheet (180), so the suggested 450 never appears.
    assert not r.is_handoff
    assert "180" in r.text and "450" not in r.text


def test_the_real_price_still_goes_out_alongside_their_number(monkeypatch, garage):
    stub(monkeypatch, PRICE_READ, "Oil change, Toyota Camry 2019 - AED 180.")
    r = engine.build_reply(garage, "oil change camry 2019, friend paid 450?")
    assert not r.is_handoff
    assert "180" in r.text


def test_their_car_year_is_echoed_on_a_price_turn(monkeypatch, garage):
    """The reply names their car back, year included, so a wrong match is visible."""
    stub(monkeypatch, PRICE_READ, "ignored")
    r = engine.build_reply(garage, "oil change camry 2019?")
    assert not r.is_handoff
    assert "Toyota Camry 2019" in r.text and "2019" in r.text


def test_numbers_from_the_customer_are_still_fine_when_no_price_is_involved(monkeypatch, garage):
    stub(monkeypatch,
         {"intent": "symptom", "language": "en", "symptom": "noise", "confidence": 0.9},
         "Noted, Camry 2019. Can you bring it in for a free inspection?")
    assert not engine.build_reply(garage, "noise on my camry 2019").is_handoff


def test_info_turn_still_blocks_an_invented_number(monkeypatch, garage):
    """Owner info may carry money, but the model still cannot introduce a figure
    that is not in the facts — the digit allowlist bites regardless of money_ok."""
    stub(monkeypatch,
         {"intent": "info", "language": "en", "info_topic": "warranty", "confidence": 0.9},
         "Our warranty is 6 months, and by the way an oil change is AED 999.")
    r = engine.build_reply(garage, "what warranty do you give?")
    assert r.is_handoff and "999" not in r.text


# --- casual small talk: warm, no handover, still no facts -------------------

def test_smalltalk_gets_a_warm_reply_not_a_handover(monkeypatch, garage):
    stub(monkeypatch, {"intent": "smalltalk", "language": "en", "confidence": 0.9},
         "You're welcome! Anything else for your car?")
    r = engine.build_reply(garage, "thanks bro")
    assert not r.is_handoff
    assert r.text == "You're welcome! Anything else for your car?"


def test_smalltalk_still_cannot_state_a_price(monkeypatch, garage):
    """Even being casual, the model can't smuggle in a number."""
    stub(monkeypatch, {"intent": "smalltalk", "language": "en", "confidence": 0.9},
         "No problem! By the way an oil change is AED 200.")
    r = engine.build_reply(garage, "ok thanks")
    assert r.is_handoff and "200" not in r.text


def test_a_real_out_of_scope_question_still_hands_over(monkeypatch, garage):
    stub(monkeypatch, {"intent": "other", "language": "en", "confidence": 0.9},
         "Sure, we fix motorbikes too.")
    r = engine.build_reply(garage, "do you fix motorbikes?")
    assert r.is_handoff


def test_irrelevant_nonsense_gets_a_friendly_redirect_not_a_handover(monkeypatch, garage):
    stub(monkeypatch, {"intent": "irrelevant", "language": "en", "confidence": 0.9}, "ignored")
    r = engine.build_reply(garage, "do you sell pizza?")
    assert not r.is_handoff              # owner is NOT pinged over nonsense
    assert "car" in r.text.lower()       # nudges them back to car service


# --- scope limits: "what we don't service" ----------------------------------

GCC_ONLY = "GCC-spec vehicles only, no US or import-spec cars"


def _with_restriction(garage, text=GCC_ONLY):
    g = {**garage, "info": {**garage["info"], "restrictions": text}}
    return g


def test_restriction_is_stated_with_the_first_price(monkeypatch, garage):
    stub(monkeypatch, PRICE_READ, "unused - price built in code")
    r = engine.build_reply(_with_restriction(garage), "oil change camry 2019?")
    assert not r.is_handoff
    assert GCC_ONLY in r.text            # scope stated up front
    assert "180" in r.text               # and still the price
    assert "Please note" in r.text


def test_restriction_is_not_repeated_when_already_said(monkeypatch, garage):
    stub(monkeypatch, PRICE_READ, "unused")
    history = [{"role": "assistant", "content": "Please note: %s" % GCC_ONLY}]
    r = engine.build_reply(_with_restriction(garage), "and brakes?", history)
    assert GCC_ONLY not in r.text        # said once, not on every quote
    assert "180" in r.text


def test_blank_or_todo_restriction_is_never_shown(monkeypatch, garage):
    stub(monkeypatch, PRICE_READ, "unused")
    for stub_val in ("", "  ", "TODO — ask him", "none"):
        r = engine.build_reply(_with_restriction(garage, stub_val), "oil change camry 2019?")
        assert "Please note" not in r.text
        assert "180" in r.text


def test_restriction_reaches_the_composer_on_a_non_price_turn(monkeypatch, garage):
    seen = {}

    def draft(facts):
        seen["facts"] = facts
        return "Hi! How can I help with your car?"

    stub(monkeypatch, {"intent": "greeting", "language": "en", "confidence": 0.9}, draft)
    engine.build_reply(_with_restriction(garage), "hi")
    assert GCC_ONLY in seen["facts"]     # composer is told the scope
    assert "does NOT service" in seen["facts"]


def test_no_restriction_means_no_scope_fact(monkeypatch, garage):
    seen = {}

    def draft(facts):
        seen["facts"] = facts
        return "Hi there!"

    stub(monkeypatch, {"intent": "greeting", "language": "en", "confidence": 0.9}, draft)
    engine.build_reply(garage, "hi")     # plain fixture, no restrictions key
    assert "does NOT service" not in seen["facts"]
