"""Commands the owner sends from his own phone.

He is not going to learn a syntax, so these are forgiving: case, spacing, a
leading slash or not, and a phone number written any of the ways a Dubai number
gets written. Anything not recognised is not a command - it is just him talking
to a customer, and must be treated as such.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

HELP = (
    "Commands:\n"
    "/bot off 0501234567 - I stop replying in that chat\n"
    "/bot on 0501234567 - I start again\n"
    "/bot off - I stop replying to everyone\n"
    "/bot on - I start again for everyone\n"
    "/status - today's numbers"
)


@dataclass(frozen=True)
class Command:
    action: str                    # on | off | status | help
    number: str | None = None      # normalised, no plus, or None for "everyone"


_PATTERN = re.compile(
    r"""^\s*/?\s*
        (?:bot\s+(?P<action>on|off)|(?P<other>status|help))
        \s*(?P<number>[\d\s\-()+]+)?\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def parse(text: str, default_country: str = "971") -> Command | None:
    """Read one owner message as a command, or None if it is not one."""
    if not text:
        return None

    match = _PATTERN.match(text)
    if not match:
        return None

    action = (match.group("action") or match.group("other") or "").lower()
    raw = match.group("number")
    if action in ("status", "help") and raw:
        return None  # "/status 050..." is not a command we know

    return Command(action=action, number=normalise(raw, default_country) if raw else None)


def normalise(number: str | None, default_country: str = "971") -> str | None:
    """0501234567, +971 50 123 4567, 971501234567 all become 971501234567.

    WhatsApp gives us numbers without a plus, so that is the form we store and
    compare. A number we cannot make sense of comes back as None rather than as
    a wrong guess - releasing the wrong conversation is worse than saying no.
    """
    if not number:
        return None

    digits = re.sub(r"\D", "", number)
    if not digits:
        return None

    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):                  # local form: 050...
        digits = default_country + digits[1:]
    elif not digits.startswith(default_country) and len(digits) <= 9:
        digits = default_country + digits       # bare 50 123 4567

    return digits if 8 <= len(digits) <= 15 else None
