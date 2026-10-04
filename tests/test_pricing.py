"""Rule 1, at the lookup layer: a price is retrieved or it does not exist."""
import pytest

from app import pricing


def test_fixed_price_is_quoted_verbatim(sheet):
    q = pricing.quote(sheet, "oil_change", "sedan")
    assert q.text == "180"
    assert q.display == "AED 180"
    assert q.notes == "Includes filter"


def test_a_range_stays_a_range(sheet):
    """Never averaged, never rounded, never turned into 'about 500'."""
    q = pricing.quote(sheet, "brake_pads_front", "sedan")
    assert q.text == "400-600"
    assert q.display == "AED 400-600"


def test_free_is_not_given_a_currency(sheet):
    assert pricing.quote(sheet, "inspection", "suv").display == "Free"


def test_unfilled_price_is_not_quotable(sheet):
    """A TODO on the sheet is a handoff, not a blank space to fill in."""
    with pytest.raises(pricing.NotOnSheet):
        pricing.quote(sheet, "brake_pads_front", "luxury")


def test_unknown_service_is_not_quotable(sheet):
    with pytest.raises(pricing.NotOnSheet):
        pricing.quote(sheet, "gearbox_rebuild", "sedan")


def test_missing_service_is_not_quotable(sheet):
    with pytest.raises(pricing.NotOnSheet):
        pricing.quote(sheet, None, "sedan")


def test_unknown_category_is_not_quotable(sheet):
    """No 'closest category' fallback. Unknown car means ask, not guess."""
    with pytest.raises(pricing.NotOnSheet):
        pricing.quote(sheet, "oil_change", None)
    with pytest.raises(pricing.NotOnSheet):
        pricing.quote(sheet, "oil_change", "pickup")


def test_model_override_beats_the_classifier(sheet):
    """The garage prices a Patrol as an SUV; that wins over whatever was guessed."""
    q = pricing.quote(sheet, "oil_change", "sedan", make="Nissan", model="Patrol")
    assert q.category == "suv"
    assert q.text == "240"


def test_service_name_follows_the_language(sheet):
    assert pricing.quote(sheet, "oil_change", "sedan", language="ar").service_name == "تغيير الزيت"
    # falls back to English rather than failing when a language is missing
    assert pricing.quote(sheet, "oil_change", "sedan", language="hi").service_name == "Oil change"
