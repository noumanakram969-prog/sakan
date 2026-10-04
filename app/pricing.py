"""Price lookup. Plain code, no model involved.

Rule 1 lives here: a price the bot sends must have come out of this module,
which reads it verbatim from the garage's prices.yaml. Nothing generates a
number; this only ever retrieves one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CATEGORIES = ("sedan", "suv", "luxury")

# Values that mean "the owner has not filled this in" — never quotable.
UNSET = {"", "todo", "tbd", "-", "n/a", "none", "null"}


@dataclass(frozen=True)
class Quote:
    service_id: str
    service_name: str
    category: str
    text: str          # exactly as written in the sheet, e.g. "450" or "400-600"
    display: str       # what the customer sees, e.g. "AED 450" or "Free"
    notes: str | None = None


class NotOnSheet(Exception):
    """The service, the car, or the price is not on the sheet.

    Every raise of this ends the same way: free inspection + owner alert.
    Never a guess.
    """


class NeedCar(NotOnSheet):
    """We know the service, but not which car — so we can't pick sedan/SUV/luxury.

    This is NOT off-sheet: the answer is to ask the customer for their car, not to
    hand over. A subclass of NotOnSheet so old `except NotOnSheet` still catches it.
    """


def _services(sheet: dict[str, Any]) -> list[dict[str, Any]]:
    return sheet.get("services") or []


def find_service(sheet: dict[str, Any], service_id: str | None) -> dict[str, Any]:
    if not service_id:
        raise NotOnSheet("no service identified")
    for svc in _services(sheet):
        if svc.get("id") == service_id:
            return svc
    raise NotOnSheet("service %r is not on the sheet" % service_id)


def service_ids(sheet: dict[str, Any]) -> list[str]:
    return [s["id"] for s in _services(sheet) if s.get("id")]


def category_for_model(sheet: dict[str, Any], make: str | None, model: str | None) -> str | None:
    """Per-model override, when a garage prices that way. None means 'no override'."""
    overrides = sheet.get("model_categories") or {}
    for key, cat in overrides.items():
        needle = key.lower()
        for field in (model, make):
            if field and needle in field.lower():
                return cat if cat in CATEGORIES else None
    return None


# Built-in car -> class, so we don't depend on the model to know that a Patrol is
# an SUV or a Mercedes is luxury. Keys are matched as substrings against the
# make/model text in ANY language (English, Roman, Arabic). This is the
# deterministic backstop for the classifier's `car_category`.
_BUILTIN_MODELS: dict[str, str] = {
    # sedan
    "camry": "sedan", "كامري": "sedan", "corolla": "sedan", "كورولا": "sedan",
    "civic": "sedan", "سيفيك": "sedan", "accord": "sedan", "اكورد": "sedan",
    "sunny": "sedan", "صني": "sedan", "altima": "sedan", "التيما": "sedan",
    "accent": "sedan", "اكسنت": "sedan", "sonata": "sedan", "سوناتا": "sedan",
    "elantra": "sedan", "النترا": "sedan", "yaris": "sedan", "يارس": "sedan",
    "lancer": "sedan", "لانسر": "sedan", "sentra": "sedan",
    # suv
    "patrol": "suv", "باترول": "suv", "land cruiser": "suv", "لاندكروزر": "suv",
    "لاند كروزر": "suv", "prado": "suv", "برادو": "suv", "pajero": "suv", "باجيرو": "suv",
    "x-trail": "suv", "xtrail": "suv", "اكستريل": "suv", "tucson": "suv", "توسان": "suv",
    "santa fe": "suv", "سنتافي": "suv", "explorer": "suv", "اكسبلورر": "suv",
    "pathfinder": "suv", "باثفايندر": "suv", "fortuner": "suv", "فورتشنر": "suv",
    "kia sportage": "suv", "sportage": "suv", "durango": "suv", "tahoe": "suv",
    # luxury
    "mercedes": "luxury", "مرسيدس": "luxury", "benz": "luxury", "بنز": "luxury",
    "bmw": "luxury", "بي ام دبليو": "luxury", "audi": "luxury", "اودي": "luxury", "أودي": "luxury",
    "lexus": "luxury", "لكزس": "luxury", "porsche": "luxury", "بورش": "luxury",
    "range rover": "luxury", "رنج روفر": "luxury", "jaguar": "luxury", "جاكوار": "luxury",
    "bentley": "luxury", "بنتلي": "luxury", "maserati": "luxury", "مازيراتي": "luxury",
    "land rover": "luxury",
}


def builtin_category(make: str | None, model: str | None) -> str | None:
    """Deterministic car class from the make/model text, any language. None if unknown."""
    hay = ("%s %s" % (make or "", model or "")).lower()
    if not hay.strip():
        return None
    for needle, cat in _BUILTIN_MODELS.items():
        if needle in hay:
            return cat
    return None


def quote(
    sheet: dict[str, Any],
    service_id: str | None,
    category: str | None,
    *,
    make: str | None = None,
    model: str | None = None,
    language: str = "en",
) -> Quote:
    """Look up one price. Raises NotOnSheet rather than returning anything vague."""
    svc = find_service(sheet, service_id)

    # Order: the garage's own model override, then whatever the classifier said,
    # then our built-in car table (deterministic, language-agnostic). Only if all
    # three fail do we not know the class.
    category = category_for_model(sheet, make, model) or category
    if category not in CATEGORIES:
        category = builtin_category(make, model)
    if category not in CATEGORIES:
        raise NeedCar("car category not identified")

    raw = (svc.get("prices") or {}).get(category)
    text = ("" if raw is None else str(raw)).strip()
    if text.lower() in UNSET:
        raise NotOnSheet(
            "no price on the sheet for %s / %s" % (service_id, category)
        )

    names = svc.get("name") or {}
    service_name = names.get(language) or names.get("en") or service_id

    # A note the owner never filled ("TODO ...") must never reach a customer.
    raw_note = str(svc.get("notes") or "").strip()
    clean_note = raw_note if (raw_note and raw_note.lower() not in UNSET
                              and not raw_note.upper().startswith("TODO")) else None

    return Quote(
        service_id=service_id,
        service_name=service_name,
        category=category,
        text=text,
        display=_display(text, sheet.get("currency", "AED")),
        notes=clean_note,
    )


def _display(text: str, currency: str) -> str:
    """Format for the customer without changing the number.

    A range stays a range. 'Free' stays 'Free'. We never round, never average,
    never turn '400-600' into 'about 500'.
    """
    if not re.search(r"\d", text):
        return text  # "Free", "On inspection", whatever the owner wrote
    if currency.lower() in text.lower():
        return text
    return "%s %s" % (currency, text)

