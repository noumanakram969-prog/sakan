"""The gate every outbound message passes through before it is sent.

Layer 1 (app/pricing.py) means the model is never asked to produce a price.
This is layer 2: even so, nothing leaves the service carrying a number that
did not come from the garage's own data or from the customer's own message.

If a reply fails here it is not repaired and not retried with a nudge. It is
replaced with the handoff line and the owner is alerted. A blocked reply is a
bug to read in the morning, not something to paper over at runtime.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Numbers that carry no pricing meaning and would otherwise trip the gate.
_ALWAYS_ALLOWED = {
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",   # counting, "2 slots"
    "12", "24", "30", "60",                                    # clock and calendar
}

_DIGITS = re.compile(r"\d+")

# A reply may only mention money if a price was actually looked up for it.
_MONEY = re.compile(r"(?i)\b(aed|dhs?|dirhams?)\b|د\.إ|€|\$")


@dataclass
class Verdict:
    ok: bool
    reason: str = ""
    offending: list[str] = field(default_factory=list)


def allowed_numbers(*sources: str | None) -> set[str]:
    """Build the allowlist from whichever sources the caller trusts for this turn.

    The customer's own message is a legitimate source for a car year or a
    quantity, but it is NOT a source once money is on the table: a customer who
    writes "my friend said 450" would otherwise have written the bot's price for
    it. On a turn carrying a quote, pass the facts only.
    """
    out: set[str] = set(_ALWAYS_ALLOWED)
    for src in sources:
        if src:
            out.update(_DIGITS.findall(src))
    return out


def check(reply: str, *, allowed: set[str], money_allowed: bool) -> Verdict:
    """Decide whether this reply may be sent.

    `money_allowed` is True only when a real Quote was retrieved for this turn.
    A reply that talks about money without one is a fabricated price by
    definition, whatever the digits say.
    """
    if not reply or not reply.strip():
        return Verdict(False, "empty reply")

    if _MONEY.search(reply) and not money_allowed:
        return Verdict(False, "mentions money with no price looked up")

    offending = sorted(n for n in _DIGITS.findall(reply) if n not in allowed)
    if offending:
        return Verdict(False, "numbers not in the source data", offending)

    return Verdict(True)


def enforce(
    reply: str,
    *,
    allowed: set[str],
    money_allowed: bool,
    fallback: str,
) -> tuple[str, Verdict]:
    """Return the message to actually send, plus why, if it was swapped.

    The fallback is the handoff line. It is deliberately the same line the bot
    uses whenever it is unsure: the customer sees consistent behaviour, and the
    owner gets a call to make.
    """
    verdict = check(reply, allowed=allowed, money_allowed=money_allowed)
    return (reply if verdict.ok else fallback), verdict
