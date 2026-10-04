"""Layer 2: nothing leaves carrying a number the facts do not support."""
from app import guard

FACTS = "- Service matched: Front brake pads\n- Price to quote, exactly as written: AED 450"
CUSTOMER = "how much for brake pads on my 2019 Camry?"
ALLOWED = guard.allowed_numbers(FACTS, CUSTOMER)


def ok(reply, money=True):
    return guard.check(reply, allowed=ALLOWED, money_allowed=money).ok


def test_the_looked_up_price_passes():
    assert ok("Front brake pads, Camry 2019 - AED 450. When suits you?")


def test_an_invented_price_is_blocked():
    assert not ok("Front brake pads are AED 480.")


def test_a_price_nudged_up_is_blocked():
    """The classic failure: right shape, wrong number."""
    assert not ok("That will be AED 4500 for the brake pads.")


def test_money_with_no_lookup_is_blocked():
    """Even with no digits at all - talking money without a quote is inventing one."""
    assert not ok("It is around fifty dirhams.", money=False)
    assert not ok("AED depends on the car.", money=False)


def test_numbers_from_the_customer_are_allowed():
    assert ok("Camry 2019, noted.", money=False)


def test_small_counting_numbers_are_allowed():
    assert ok("We have 2 slots free tomorrow.", money=False)


def test_a_phone_number_is_blocked():
    """Nothing should be dictating numbers we did not give it."""
    assert not ok("Call us on 043334444.", money=False)


def test_empty_reply_is_blocked():
    assert not ok("")
    assert not ok("   ")


def test_offending_numbers_are_reported():
    v = guard.check("AED 480 or maybe 520", allowed=ALLOWED, money_allowed=True)
    assert v.offending == ["480", "520"]


def test_enforce_swaps_in_the_handoff_line():
    text, verdict = guard.enforce(
        "It is AED 999.", allowed=ALLOWED, money_allowed=True, fallback="Advisor will call."
    )
    assert text == "Advisor will call."
    assert not verdict.ok


def test_enforce_passes_a_good_reply_through_untouched():
    good = "Front brake pads, Camry 2019 - AED 450."
    text, verdict = guard.enforce(
        good, allowed=ALLOWED, money_allowed=True, fallback="Advisor will call."
    )
    assert text == good and verdict.ok
