"""The only place a model is spoken to. Anthropic or OpenAI, chosen by config.

Two calls per turn at most: classify what the customer wants, then compose a
reply from facts that were looked up in between. The model never sees the
price sheet, so it cannot quote from it directly — that guarantee is enforced
in app/pricing.py and app/guard.py, not here, so it holds whichever model runs.

Prompts live in prompts/ as files. Nothing prompt-shaped belongs in here.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import settings

log = logging.getLogger(__name__)

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

MAX_HISTORY = 8  # turns of context; a garage chat is short

# A customer is watching a "typing" indicator that is not there. Better to hand
# over in twenty seconds than to hold the turn open while a request hangs.
TIMEOUT_SECONDS = 20.0
MAX_RETRIES = 2


@lru_cache(maxsize=None)
def prompt(name: str) -> str:
    return (PROMPTS / ("%s.md" % name)).read_text(encoding="utf-8")


class LLMUnavailable(RuntimeError):
    """No key, no network, bad response. Always ends in a handoff, never a guess."""


# --------------------------------------------------------------------------- clients

@lru_cache(maxsize=1)
def _anthropic_client(api_key: str):
    import anthropic  # imported lazily so tests run without the package configured

    return anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)


@lru_cache(maxsize=1)
def _openai_client(api_key: str):
    import openai  # lazy import

    return openai.OpenAI(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)


def _complete(system: str, messages: list[dict[str, str]], max_tokens: int, want_json: bool,
              model: str | None = None) -> str:
    """One model call, provider-agnostic. Returns the assistant's text.

    Any failure — no key, bad network, a refusal — becomes LLMUnavailable, and
    the engine turns that into a handoff. The model is never trusted to fail
    safely on its own.
    """
    provider = (settings.llm_provider or "anthropic").lower()

    try:
        if provider == "openai":
            if not settings.openai_api_key:
                raise LLMUnavailable("no OPENAI_API_KEY")
            client = _openai_client(settings.openai_api_key)
            kwargs: dict[str, Any] = {
                "model": model or settings.openai_model,
                "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}] + messages,
            }
            if want_json:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()

        # default: anthropic
        if not settings.anthropic_api_key:
            raise LLMUnavailable("no ANTHROPIC_API_KEY")
        client = _anthropic_client(settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        ).strip()

    except LLMUnavailable:
        raise
    except Exception as exc:  # network, rate limit, refusal, anything
        raise LLMUnavailable("%s: %s" % (provider, exc)) from exc


# --------------------------------------------------------------------------- the two calls

def classify(
    message: str,
    service_ids: list[str],
    history: list[dict[str, str]] | None = None,
    *,
    today: datetime | None = None,
    timezone: str = "Asia/Dubai",
) -> dict[str, Any]:
    """What is the customer asking? Structured, no prose, no prices.

    `today` is the garage's local date. Without it the classifier cannot turn
    "Saturday" into a date, and every relative day would be a guess.
    """
    today = today or datetime.now()
    system = (
        prompt("classify")
        .replace("{{today}}", today.strftime("%Y-%m-%d"))
        .replace("{{weekday}}", today.strftime("%A"))
        .replace("{{timezone}}", timezone)
        + "\n\nService ids for this garage:\n"
        + "\n".join("- %s" % s for s in service_ids)
    )
    messages = list(history or [])[-MAX_HISTORY:] + [{"role": "user", "content": message}]
    raw = _complete(system, messages, max_tokens=400, want_json=True,
                    model=settings.openai_classify_model or None)
    return _parse_json(raw)


def _parse_json(raw: str) -> dict[str, Any]:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable("classifier did not return JSON: %r" % raw[:200]) from exc
    if not isinstance(data, dict):
        raise LLMUnavailable("classifier returned %s, not an object" % type(data).__name__)
    return data


def compose(garage_name: str, facts: str, message: str, history: list[dict[str, str]] | None = None) -> str:
    """Write the reply from the facts. The model sees no price sheet, only what was looked up."""
    system = prompt("system").replace("{{garage_name}}", garage_name).replace("{{facts}}", facts)
    messages = list(history or [])[-MAX_HISTORY:] + [{"role": "user", "content": message}]
    return _complete(system, messages, max_tokens=300, want_json=False)
