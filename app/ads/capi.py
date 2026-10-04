"""Conversions API - server-side events.

Why this exists at all: the browser pixel is blocked, cleared and ad-blocked
often enough that a meaningful share of conversions never reach Meta, so the
optimiser learns from a biased sample. Sending the same events from the server
fixes the record. It also lets events that never touch a browser be reported at
all - and in this stack that is most of them, because a lead that arrives on
WhatsApp and books through the agent has no web page anywhere in it.

Two details decide whether it works:

* **Hashing.** Every piece of personal data is normalised then SHA-256'd before
  it leaves. Meta requires it, and it means a leaked payload is not a leaked
  customer list. Raw PII never goes over the wire from here - the hashing is not
  optional and there is no flag to skip it.

* **event_id.** Browser and server send the same id for the same event so Meta
  deduplicates. Without it, every conversion seen by both is counted twice, CPL
  looks half what it is, and the budget rules act on a fiction.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .client import GraphClient

log = logging.getLogger("mistri.ads")

# Fields Meta expects hashed, with the normalisation each one needs first.
_HASHED = {"em", "ph", "fn", "ln", "ct", "st", "zp", "country", "external_id"}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalise(key: str, value: str) -> str:
    v = str(value).strip().lower()
    if key == "em":
        return v
    if key == "ph":
        # digits only, country code included, no leading +, no 00 prefix
        v = re.sub(r"\D", "", v)
        return v.lstrip("0") if v.startswith("00") else v
    if key in {"fn", "ln", "ct", "st"}:
        return re.sub(r"[^a-z]", "", v)
    if key == "zp":
        return re.sub(r"[^a-z0-9]", "", v)
    if key == "country":
        return v[:2]
    return v


def hash_user_data(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise and hash. Anything already a 64-char hex digest is left alone,
    so calling this twice cannot double-hash and silently break matching."""
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if v in (None, ""):
            continue
        if k in _HASHED:
            s = str(v)
            out[k] = s.lower() if _is_sha256(s) else _sha256(_normalise(k, s))
        else:
            # client_ip_address, client_user_agent, fbc, fbp - sent as-is by design
            out[k] = v
    return out


def _is_sha256(s: str) -> bool:
    return len(s) == 64 and re.fullmatch(r"[0-9a-fA-F]{64}", s) is not None


@dataclass
class Event:
    event_name: str
    user_data: dict[str, Any]
    event_time: int = field(default_factory=lambda: int(time.time()))
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    action_source: str = "website"
    event_source_url: str | None = None
    custom_data: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        p: dict[str, Any] = {
            "event_name": self.event_name,
            "event_time": self.event_time,
            "event_id": self.event_id,
            "action_source": self.action_source,
            "user_data": hash_user_data(self.user_data),
        }
        if self.event_source_url:
            p["event_source_url"] = self.event_source_url
        if self.custom_data:
            p["custom_data"] = self.custom_data
        return p


class ConversionsAPI:
    def __init__(
        self,
        client: GraphClient,
        pixel_id: str,
        *,
        test_event_code: str | None = None,
    ) -> None:
        self.client = client
        self.pixel_id = pixel_id
        # With a test code set, events land in Test Events only and never touch
        # reporting or attribution. Safe to leave on while building.
        self.test_event_code = test_event_code

    def send(self, events: list[Event]) -> dict[str, Any]:
        import json

        payload: dict[str, Any] = {"data": json.dumps([e.to_payload() for e in events])}
        if self.test_event_code:
            payload["test_event_code"] = self.test_event_code

        res = self.client.post(f"{self.pixel_id}/events", **payload)
        log.info(
            "capi sent %d event(s) -> received=%s%s",
            len(events), res.get("events_received"),
            " [TEST]" if self.test_event_code else "",
        )
        return res

    # -- the events this stack actually fires -------------------------------

    def lead(
        self,
        *,
        phone: str | None = None,
        email: str | None = None,
        event_id: str | None = None,
        value: float | None = None,
        currency: str = "AED",
        source: str = "whatsapp",
        **user_data: Any,
    ) -> dict[str, Any]:
        """A new qualified lead.

        action_source is "business_messaging" when it came from WhatsApp - Meta
        attributes a chat lead differently from a web form, and reporting it as
        a website event quietly misattributes the campaign that produced it.
        """
        ud: dict[str, Any] = dict(user_data)
        if phone:
            ud["ph"] = phone
        if email:
            ud["em"] = email

        custom: dict[str, Any] = {"lead_source": source}
        if value is not None:
            custom |= {"value": value, "currency": currency}

        ev = Event(
            event_name="Lead",
            user_data=ud,
            action_source="business_messaging" if source == "whatsapp" else "website",
            custom_data=custom,
        )
        if event_id:
            ev.event_id = event_id
        return self.send([ev])

    def booking(
        self,
        *,
        phone: str | None = None,
        value: float | None = None,
        currency: str = "AED",
        service: str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """A lead that became a booking - the event worth optimising towards."""
        ud: dict[str, Any] = {}
        if phone:
            ud["ph"] = phone

        custom: dict[str, Any] = {}
        if value is not None:
            custom |= {"value": value, "currency": currency}
        if service:
            custom["content_name"] = service

        ev = Event(
            event_name="Schedule",
            user_data=ud,
            action_source="business_messaging",
            custom_data=custom,
        )
        if event_id:
            ev.event_id = event_id
        return self.send([ev])
