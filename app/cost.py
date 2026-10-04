"""What the agent costs to run, per conversation and per month.

An agent that answers every message is a variable cost on every message, and the
two ways that bill surprises you are both cheap to prevent:

* **A runaway conversation.** A loop, a bored tester, or someone replying to
  every message with "ok" quietly runs up hundreds of calls against one number.
  The ceiling here is per conversation, so one bad thread cannot spend the month.
* **A quiet drift.** Nobody notices a 30% rise in tokens per reply until the
  invoice arrives, because every individual reply still looks fine.

So every call is metered where it is made, the spend is attributed to the
conversation that caused it, and the caps are checked *before* the call rather
than reported after it. Going over a cap is not an error: it hands the customer
to a human, which is what the system does whenever it cannot answer safely.

Prices are per million tokens, in USD, and they are data rather than code -
`PRICES` is overridable from the environment, because a provider's price list
changes without asking us and a wrong constant silently produces confident,
wrong numbers.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("sakan.cost")

# USD per million tokens: (input, output). Checked against the providers'
# published pricing on 4 October 2026.
PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-5": (15.00, 75.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}

# When a model is not in the table, bill it at the most expensive rate we know
# rather than at zero. An unknown model that reports as free is how an overrun
# goes unnoticed; one that reports as expensive gets looked at.
UNKNOWN_PRICE = max(PRICES.values(), key=lambda p: p[1])


def _load_price_overrides() -> None:
    raw = os.environ.get("LLM_PRICES_JSON", "").strip()
    if not raw:
        return
    try:
        for model, pair in json.loads(raw).items():
            PRICES[model] = (float(pair[0]), float(pair[1]))
        log.info("loaded %d price override(s) from LLM_PRICES_JSON", len(json.loads(raw)))
    except Exception:
        log.warning("LLM_PRICES_JSON is not valid JSON of {model: [in, out]} - ignored")


_load_price_overrides()


def price_of(model: str) -> tuple[float, float]:
    """Longest-prefix match, so a dated snapshot bills at its family's rate."""
    if model in PRICES:
        return PRICES[model]
    best: tuple[str, tuple[float, float]] | None = None
    for known, pair in PRICES.items():
        if model.startswith(known) and (best is None or len(known) > len(best[0])):
            best = (known, pair)
    if best:
        return best[1]
    log.warning("no price for model %r - billing at the highest known rate", model)
    return UNKNOWN_PRICE


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    cin, cout = price_of(model)
    return (input_tokens * cin + output_tokens * cout) / 1_000_000


@dataclass
class Caps:
    """The ceilings. Deliberately small numbers - a property enquiry that needs
    forty model calls has gone wrong, and a human should see it."""

    calls_per_conversation_per_day: int = 40
    usd_per_conversation_per_day: float = 0.50
    usd_per_month: float = 200.00


class CapExceeded(Exception):
    """Raised before a call, never after. Carries which ceiling and by how much,
    because 'over budget' with no number is not actionable."""

    def __init__(self, which: str, used: float, limit: float) -> None:
        self.which, self.used, self.limit = which, used, limit
        super().__init__(f"{which}: {used:.4g} of {limit:.4g}")


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "usd": round(self.usd, 5),
        }


class Meter:
    """Per-conversation and per-month spend.

    In memory, with an optional JSON file so a restart does not forget the
    month. A deployment with a database keeps the same interface and writes
    rows instead; nothing above this class knows which it is.
    """

    def __init__(self, caps: Caps | None = None, *, path: Path | str | None = None) -> None:
        self.caps = caps or Caps()
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        # (conversation, YYYY-MM-DD) -> Usage
        self._daily: dict[tuple[str, str], Usage] = defaultdict(Usage)
        # YYYY-MM -> Usage
        self._monthly: dict[str, Usage] = defaultdict(Usage)
        self._load()

    # -- the two questions ------------------------------------------------

    def check(self, conversation: str, *, today: date | None = None) -> None:
        """Called before a model call. Raises rather than returning a flag, so
        a caller cannot forget to look at the answer."""
        d = (today or _utcdate())
        day, month = d.isoformat(), d.strftime("%Y-%m")

        with self._lock:
            conv = self._daily.get((conversation, day), Usage())
            mon = self._monthly.get(month, Usage())

        if conv.calls >= self.caps.calls_per_conversation_per_day:
            raise CapExceeded("calls per conversation today",
                              conv.calls, self.caps.calls_per_conversation_per_day)
        if conv.usd >= self.caps.usd_per_conversation_per_day:
            raise CapExceeded("usd per conversation today",
                              conv.usd, self.caps.usd_per_conversation_per_day)
        if mon.usd >= self.caps.usd_per_month:
            raise CapExceeded("usd this month", mon.usd, self.caps.usd_per_month)

    def record(
        self,
        conversation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        *,
        today: date | None = None,
    ) -> float:
        """Meter one call. Returns what it cost."""
        usd = cost_usd(model, input_tokens, output_tokens)
        d = (today or _utcdate())
        day, month = d.isoformat(), d.strftime("%Y-%m")

        with self._lock:
            for bucket in (self._daily[(conversation, day)], self._monthly[month]):
                bucket.calls += 1
                bucket.input_tokens += input_tokens
                bucket.output_tokens += output_tokens
                bucket.usd += usd
            month_total = self._monthly[month].usd
            conv_total = self._daily[(conversation, day)].usd

        log.info(
            "llm %s in=%d out=%d cost=$%.5f conv=$%.4f month=$%.2f",
            model, input_tokens, output_tokens, usd, conv_total, month_total,
        )

        # Warn on the way up, not only at the wall.
        if month_total >= self.caps.usd_per_month * 0.8:
            log.warning("month spend $%.2f is past 80%% of the $%.2f cap",
                        month_total, self.caps.usd_per_month)

        self._save()
        return usd

    # -- reporting ---------------------------------------------------------

    def conversation(self, conversation: str, *, today: date | None = None) -> Usage:
        d = (today or _utcdate()).isoformat()
        with self._lock:
            return self._daily.get((conversation, d), Usage())

    def month(self, month: str | None = None) -> Usage:
        m = month or _utcdate().strftime("%Y-%m")
        with self._lock:
            return self._monthly.get(m, Usage())

    def report(self, month: str | None = None) -> dict[str, Any]:
        m = month or _utcdate().strftime("%Y-%m")
        u = self.month(m)
        with self._lock:
            convs = sorted(
                ((c, v) for (c, d), v in self._daily.items() if d.startswith(m)),
                key=lambda kv: -kv[1].usd,
            )[:10]
        return {
            "month": m,
            "total": u.as_dict(),
            "cap_usd": self.caps.usd_per_month,
            "used_pct": round(u.usd / self.caps.usd_per_month * 100, 1) if self.caps.usd_per_month else 0.0,
            "cost_per_call": round(u.usd / u.calls, 5) if u.calls else 0.0,
            "top_conversations": [
                {"conversation": _redact(c), **v.as_dict()} for c, v in convs
            ],
        }

    # -- persistence -------------------------------------------------------

    def _save(self) -> None:
        if not self._path:
            return
        try:
            with self._lock:
                blob = {
                    "daily": {f"{c}|{d}": v.as_dict() for (c, d), v in self._daily.items()},
                    "monthly": {m: v.as_dict() for m, v in self._monthly.items()},
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                }
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(blob), encoding="utf-8")
            tmp.replace(self._path)          # atomic: never a half-written ledger
        except OSError:
            log.warning("could not persist the cost ledger to %s", self._path)

    def _load(self) -> None:
        if not self._path or not self._path.exists():
            return
        try:
            blob = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("cost ledger at %s is unreadable - starting fresh", self._path)
            return
        for key, v in (blob.get("daily") or {}).items():
            conv, _, day = key.rpartition("|")
            self._daily[(conv, day)] = _usage(v)
        for m, v in (blob.get("monthly") or {}).items():
            self._monthly[m] = _usage(v)


def _usage(v: dict[str, Any]) -> Usage:
    return Usage(
        calls=int(v.get("calls", 0)),
        input_tokens=int(v.get("input_tokens", 0)),
        output_tokens=int(v.get("output_tokens", 0)),
        usd=float(v.get("usd", 0.0)),
    )


def _utcdate() -> date:
    return datetime.now(timezone.utc).date()


def _redact(number: str) -> str:
    """A cost report is not a reason to put customer numbers in a log."""
    return f"•••{number[-4:]}" if len(number) > 4 else "•••"


def tokens_from_response(resp: Any) -> tuple[int, int]:
    """Read the usage the provider reported, rather than estimating it.

    Anthropic puts it on `usage.input_tokens`/`output_tokens`, OpenAI on
    `usage.prompt_tokens`/`completion_tokens`. Returns (0, 0) when a provider
    gives nothing, which the caller logs rather than guessing around.
    """
    usage = getattr(resp, "usage", None)
    if usage is None:
        return 0, 0
    for a, b in (("input_tokens", "output_tokens"), ("prompt_tokens", "completion_tokens")):
        i, o = getattr(usage, a, None), getattr(usage, b, None)
        if i is not None or o is not None:
            return int(i or 0), int(o or 0)
    return 0, 0
